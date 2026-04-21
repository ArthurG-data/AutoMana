import importlib, logging
from typing import  Optional
from contextlib import asynccontextmanager
from automana.core.QueryExecutor import QueryExecutor
from automana.core.service_modules import SERVICE_MODULES
from automana.core.service_registry import ServiceRegistry
from automana.core.storage import StorageService

from automana.core.logging_context import set_service_path

logger = logging.getLogger(__name__)


class ServiceManager:
    """Singleton class to manage services and their dependencies"""
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ServiceManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, connection_pool, query_executor: Optional[QueryExecutor] = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self.query_executor = query_executor
        self.connection_pool = connection_pool
        self._initialized = True

        self._discover_services()
       
    def _discover_services(self):
        """Import all service modules to register them"""
        from automana.core.settings import get_settings
        from automana.core.data_loader import load_services
        settings = get_settings()
        module_namespace = getattr(settings, "modules_namespace")
        modules = SERVICE_MODULES.get(module_namespace, [])
        logger.info(
            "loading_service_modules",
            extra={
                "action": "load_service_modules",
                "namespace": module_namespace,
                "modules_count": len(modules),
            },
        )
        try:
            load_services(modules)
        except Exception as e:
            logger.exception(
                "service_module_load_failed",
                extra={
                    "action": "load_service_modules",
                    "namespace": module_namespace,
                    "modules_count": len(modules),
                },
            )
            raise RuntimeError("Error loading service modules") from e

    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection from the pool"""
        async with self.connection_pool.acquire() as connection:
            yield connection

    @asynccontextmanager
    async def transaction(self):
        """Execute operations in a transaction"""
        connection = None
        try:
            connection = await self.connection_pool.acquire()
            transaction = connection.transaction()
            await transaction.start()
            try:
                yield connection
                await transaction.commit()
                logger.debug("Transaction committed")
            except Exception as e:
                await transaction.rollback()
                logger.debug("Transaction rolled back")
                raise
        finally:
            if connection is not None:
                await self.connection_pool.release(connection)


    @classmethod
    async def initialize(cls, connection_pool, query_executor: QueryExecutor = None):
        """Initialize the singleton instance with dependencies"""
        try:
            instance = cls(connection_pool, query_executor)
            logger.info(
                "service_manager_initialized",
                extra={
                    "action": "initialize_service_manager",
                    "registered_services": len(ServiceRegistry.list_services()),
                },
            )
            return instance
        except Exception as e:
            logger.exception(
                "service_manager_initialization_failed",
                extra={"action": "initialize_service_manager"},
            )
            raise
    

    @staticmethod
    def get_service_function(path: str):
        """
        Given a service path (e.g., "staging.scryfall.get_bulk_data_uri"),
        return the actual function object registered for that path.
        """
        from automana.core.service_registry import ServiceRegistry
        service_config = ServiceRegistry.get(path)
        if not service_config:
            raise ValueError(f"Service not found: {path}")
        # Dynamically import the module and get the function
        import importlib
        module = importlib.import_module(service_config.module)
        return getattr(module, service_config.function)
    
    

    @staticmethod
    def get_storage_service(storage_name: str) -> StorageService:
        """Resolve a named storage to a StorageService instance.

        Looks up the logical name in the named-storage registry to find
        the backend type and its config, then instantiates accordingly.
        """
        from automana.core.storage import StorageService
        from automana.core.settings import get_settings
        from pathlib import Path
        import importlib

        storage_config = ServiceRegistry.get_storage(storage_name)
        if not storage_config:
            raise ValueError(f"Unknown storage name: {storage_name!r}")

        backend_name = storage_config["backend"]
        backend_info = ServiceRegistry.get_storage_backend(backend_name)
        if not backend_info:
            raise ValueError(f"Unknown storage backend: {backend_name!r}")

        module = importlib.import_module(backend_info[0])
        backend_class = getattr(module, backend_info[1])

        if backend_name == "local":
            subpath = storage_config.get("subpath", "")
            base_path = Path(get_settings().data_dir) / subpath
            backend = backend_class(base_path=str(base_path))
        else:
            config = {k: v for k, v in storage_config.items() if k != "backend"}
            backend = backend_class(**config)

        return StorageService(backend)

    @classmethod
    async def execute_service(cls, service_path: str, **kwargs):
        """Execute a service by path with provided parameters"""
        if cls._instance is None or not cls._instance._initialized:
            raise RuntimeError("ServiceManager not initialized")

        logger.info(
            "service_execution_requested",
            extra={
                "action": "execute_service",
                "service_path": service_path,
                "kwargs_keys": list(kwargs.keys()),
            },
        )
        return await cls._instance._execute_service(service_path, **kwargs)
    
    async def _execute_service(self, service_path: str, **kwargs):
        """Execute a service with its required repositories"""
        set_service_path(service_path)
        try:
        # Get service configuration from registry
            service_config = ServiceRegistry.get(service_path)
            if not service_config:
                raise ValueError(f"Service not found: {service_path}")
        
            # Import service module and get function
            try:
                module = importlib.import_module(service_config.module)
                service_method = getattr(module, service_config.function)
            except (ImportError, AttributeError) as e:
                raise ValueError(
                f"Service {service_path} could not be loaded "
                f"({service_config.module}.{service_config.function})"
            ) from e
        
        #storage
            if len(service_config.storage_services) > 0:
                kwargs["storage_service"] = self.get_storage_service(service_config.storage_services[0])
                for extra_name in service_config.storage_services[1:]:
                    kwargs[f"{extra_name}_storage_service"] = self.get_storage_service(extra_name)

            # Connection acquisition path is chosen per-service:
            #   runs_in_transaction=True  → explicit BEGIN/COMMIT around the call.
            #   runs_in_transaction=False → raw pool connection, no txn started.
            # The second mode exists for SQL that manages its own transaction
            # control (e.g. stored procs with internal COMMIT/ROLLBACK), which
            # Postgres rejects when CALL is issued from an atomic block.
            conn_ctx = (
                self.transaction() if service_config.runs_in_transaction
                else self._get_connection()
            )

            async with conn_ctx as conn:
                # Per-service command_timeout is applied on two axes:
                #
                #   1. Client-side (asyncpg). `protocol.pyx::_get_timeout_impl`
                #      reads `conn._config.command_timeout` whenever a query is
                #      dispatched without an explicit timeout, so the pool's
                #      60 s default DOES reach every `conn.execute(...)` call.
                #      `_config` is a `_ClientConfiguration` namedtuple; we
                #      swap it for a `_replace`d copy while the service runs,
                #      then restore the original on the way out. Passing
                #      `NO_TIMEOUT` explicitly is unsupported — the public
                #      `_get_timeout` wrapper `float()`s its argument before
                #      the sentinel check ever happens.
                #   2. Server-side (Postgres `statement_timeout`). Set as a
                #      belt-and-suspenders ceiling via `SET [LOCAL|SESSION]`.
                # asyncpg returns a `PoolConnectionProxy` from `pool.acquire()`.
                # The proxy has `__slots__ = ('_con', '_holder')` and a
                # `__getattr__` that reads through to the wrapped Connection,
                # but no `__setattr__` — so `conn._config = ...` fails with
                # AttributeError. We mutate the underlying Connection
                # (`conn._con`) directly, where `_config` is a real slot.
                underlying = getattr(conn, "_con", conn)
                original_config = None
                timeout_applied = False
                if service_config.command_timeout is not None:
                    original_config = underlying._config
                    underlying._config = original_config._replace(
                        command_timeout=service_config.command_timeout
                    )
                    timeout_ms = int(service_config.command_timeout * 1000)
                    # `SET LOCAL` auto-resets at COMMIT/ROLLBACK inside a txn;
                    # session-level `SET` needs an explicit RESET on the way out
                    # (see finally block) so the pooled connection doesn't
                    # leak the override to the next acquirer.
                    scope = "LOCAL" if service_config.runs_in_transaction else "SESSION"
                    await conn.execute(
                        f"SET {scope} statement_timeout = {timeout_ms}"
                    )
                    timeout_applied = True

                try:
                    repositories = {}

                    # Create DB repositories
                    for repo_type in service_config.db_repositories:
                        repo_info = ServiceRegistry.get_db_repository(repo_type)
                        if not repo_info:
                            raise ValueError(f"Unknown DB repository type: {repo_type}")

                        module_path, class_name = repo_info
                        repo_module = importlib.import_module(module_path)
                        repo_class = getattr(repo_module, class_name)
                        repositories[f"{repo_type}_repository"] = repo_class(conn, self.query_executor)

                    # Create API repositories
                    env = kwargs.pop("environment", "sandbox")
                    for repo_type in service_config.api_repositories:
                        repo_info = ServiceRegistry.get_api_repository(repo_type)
                        if not repo_info:
                            raise ValueError(f"Unknown API repository type: {repo_type}")

                        module_path, class_name = repo_info
                        repo_module = importlib.import_module(module_path)
                        repo_class = getattr(repo_module, class_name)
                        repositories[f"{repo_type}_repository"] = repo_class(environment=env)

                    logger.debug(
                        "service_execution_started",
                        extra={
                            "action": "execute_service",
                            "service_path": service_path,
                            "repository_keys": list(repositories.keys()),
                            "runs_in_transaction": service_config.runs_in_transaction,
                            "command_timeout": service_config.command_timeout,
                        },
                    )
                    result = await service_method(**repositories, **kwargs)
                finally:
                    # Restore the client-side config on the underlying
                    # Connection so the pooled proxy returns to the next
                    # acquirer without our override baked in.
                    if original_config is not None:
                        underlying._config = original_config
                    # Only session-scope server-side overrides need an explicit
                    # reset; LOCAL scope unwinds at COMMIT/ROLLBACK. Swallow
                    # errors on RESET so a broken connection can't mask the
                    # original exception.
                    if timeout_applied and not service_config.runs_in_transaction:
                        try:
                            await conn.execute("RESET statement_timeout")
                        except Exception:
                            logger.warning(
                                "failed_to_reset_statement_timeout",
                                extra={"service_path": service_path},
                            )
            return result
        except Exception:
            logger.exception(
                "service_execution_failed",
                extra={"action": "execute_service", "service_path": service_path},
            )
            raise
        finally:
            set_service_path(None)
                
    @classmethod
    async def close(cls):
        """Close all resources held by the manager"""
        if cls._instance is None:
            return
            
        cls._instance.query_executor = None
        cls._instance._initialized = False
        logger.info("ServiceManager resources closed")
