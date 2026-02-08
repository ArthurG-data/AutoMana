import importlib, logging
from typing import  Optional
from contextlib import asynccontextmanager
from backend.core.QueryExecutor import QueryExecutor
from backend.core.service_modules import SERVICE_MODULES
from backend.core.service_registry import ServiceRegistry
from backend.core.storage import StorageService

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
        from backend.core.settings import get_settings
        from backend.core.data_loader import load_services
        settings = get_settings()
        module_namespace = getattr(settings, "modules_namespace")
        logger.info(f"Loading service modules for namespace: {module_namespace}")
        modules = SERVICE_MODULES.get(module_namespace, [])
        try:
            load_services(modules)
        except Exception as e:
            raise RuntimeError(f"Error loading service modules: {e}") from e

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
            logger.info(f"ServiceManager initialized with {len(ServiceRegistry.list_services())} services")
            return instance
        except Exception as e:
            logger.error(f"Error initializing ServiceManager: {e}")
            raise
    
    '''
    @staticmethod
    def get_service_function(path: str):
        """
        Given a service path (e.g., "staging.scryfall.get_bulk_data_uri"),
        return the actual function object registered for that path.
        """
        from backend.core.service_registry import ServiceRegistry
        service_config = ServiceRegistry.get(path)
        if not service_config:
            raise ValueError(f"Service not found: {path}")
        # Dynamically import the module and get the function
        import importlib
        module = importlib.import_module(service_config.module)
        return getattr(module, service_config.function)
    
    '''

    @staticmethod
    def get_storage_service(storage_type_name: str) -> StorageService:
        """Get the service function for a given path"""
        from backend.core.storage import StorageService
        import importlib
        #get the name of the storage service from the registry
        storage_backend = ServiceRegistry.get_storage_service(storage_type_name)
        #load the storage service module
        module = importlib.import_module(storage_backend[0])
        class_backend_storage = getattr(module, storage_backend[1])
        #instanciate the storage service and return it
        instanciated_storage_backend = class_backend_storage()
        #load the correct 
        storage_service = StorageService(instanciated_storage_backend)
        return storage_service

    @classmethod
    async def execute_service(cls, service_path: str, **kwargs):
        """Execute a service by path with provided parameters"""
        if cls._instance is None or not cls._instance._initialized:
            raise RuntimeError("ServiceManager not initialized")
            
        logger.info(f"Executing service: {service_path}")
        return await cls._instance._execute_service(service_path, **kwargs)
    
    async def _execute_service(self, service_path: str, **kwargs):
        """Execute a service with its required repositories"""
        # Get service configuration from registry
        service_config = ServiceRegistry.get(service_path)
        if not service_config:
            raise ValueError(f"Service not found: {service_path}")
        
        # Import service module and get function
        try:
            module = importlib.import_module(service_config.module)
            service_method = getattr(module, service_config.function)
        except (ImportError, AttributeError) as e:
            logger.error(f"Error loading service {service_path}: {e}")
            raise ValueError(f"Service {service_path} not found: {str(e)}")
        
        #storage
        storage_service = None
        if len(service_config.storage_services) > 0:
            storage_service = self.get_storage_service(service_config.storage_services[0])
        # Execute within transaction
        async with self.transaction() as conn:
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
            for repo_type in service_config.api_repositories:
                repo_info = ServiceRegistry.get_api_repository(repo_type)
                if not repo_info:
                    raise ValueError(f"Unknown API repository type: {repo_type}")
                
                module_path, class_name = repo_info
                repo_module = importlib.import_module(module_path)
                repo_class = getattr(repo_module, class_name)
                env = kwargs.pop("environment", "sandbox")
                repositories[f"{repo_type}_repository"] = repo_class(environment=env)
            
       
            logger.debug(f"Executing {service_path} with repos: {list(repositories.keys())}")
            result = await service_method(**repositories,storage_service=storage_service, **kwargs)
        return result
    
                
    @classmethod
    async def close(cls):
        """Close all resources held by the manager"""
        if cls._instance is None:
            return
            
        cls._instance.query_executor = None
        cls._instance._initialized = False
        logger.info("ServiceManager resources closed")
