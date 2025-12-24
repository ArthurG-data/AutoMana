import importlib, logging
from typing import List, Optional, Callable
from fastapi.concurrency import asynccontextmanager
from backend.request_handling.QueryExecutor import QueryExecutor
from dataclasses import dataclass, field
from backend.core.service_registry import ServiceRegistry

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
        service_modules = [
            "backend.new_services.auth.auth_service",
            "backend.new_services.auth.session_service",
            "backend.new_services.user_management.user_service",
            "backend.new_services.user_management.role_service",
            "backend.new_services.card_catalog.card_service",
            "backend.new_services.card_catalog.set_service",
            "backend.new_services.card_catalog.collection_service",
            "backend.new_services.app_integration.ebay.auth_services",
            "backend.new_services.app_integration.ebay.browsing_services",
            "backend.new_services.app_integration.ebay.selling_services"
        ]
        for module_path in service_modules:
            try:
                importlib.import_module(module_path)
            except ImportError as e:
                logger.warning(f"Could not import service module {module_path}: {e}")


    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection from the pool"""
        async with self.connection_pool.acquire() as connection:
            yield connection

    @asynccontextmanager
    async def transaction(self):
        """Execute operations in a transaction"""
        async with self.connection_pool.acquire() as connection:
            tx = connection.transaction()
            try:
                await tx.start()
                logger.debug("Transaction started")
                yield connection
                await tx.commit()
                logger.debug("Transaction committed")
            except Exception as e:
                await tx.rollback()
                logger.debug("Transaction rolled back")
                raise
            finally:
                await connection.close()

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
            return await service_method(**repositories, **kwargs)
    
                

    
    @classmethod
    async def close(cls):
        """Close all resources held by the manager"""
        if cls._instance is None:
            return
            
        cls._instance.query_executor = None
        cls._instance._initialized = False
        logger.info("ServiceManager resources closed")
