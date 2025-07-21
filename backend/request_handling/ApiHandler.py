from backend.database.get_database import get_connection, get_async_pool_connection, init_async_pool
import importlib
from contextlib import asynccontextmanager
from backend.request_handling.utils import locate_service
from backend.request_handling.QueryExecutor import AsyncQueryExecutor, QueryExecutor
from backend.request_handling.ErrorHandler import Psycopg2ExceptionHandler
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

class ApiHandler:
    """Handles API requests and service execution with a shared query executor"""
    _instance = None
    _pool = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ApiHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, query_executor: Optional[QueryExecutor] = None, 
               ):
        
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._query_executor = query_executor
        self._repositories = {}

        self._initialized = True
    
    @classmethod
    async def initialize(cls, query_executor: QueryExecutor = None):
        """
        Initialize the singleton instance with dependencies.
        This method should be called during application startup.
        """
        try:
            instance = cls(query_executor)

            if query_executor is not None:
                instance._query_executor = query_executor
            
            # Ensure we have a query executor
            if instance._query_executor is None:
                logger.warning("Query executor not provided")
                
            logger.info("ApiHandler successfully initialized")
            return instance
        except Exception as e:
            logger.error(f"Error initializing ApiHandler: {e}")
            raise

    @classmethod
    async def execute_service(cls, service_path: str, **kwargs):
        if cls._instance is None or not hasattr(cls._instance, '_initialized'):
            logger.warning("ApiHandler not initialized, initializing now")
            await cls.initialize()
        logger.info(f"service_path: {service_path}")
        if cls._instance._query_executor is None:
            logger.warning("Query executor not initialized, initializing now")
        return await cls._instance._execute_service(service_path, **kwargs)


    async def _execute_service(self, service_path: str, **kwargs):
        #get the service method 

        service_method = locate_service(service_path)
 
        logger.info(f"Executing service: {service_path}")
        try:
            async with self._query_executor.transaction() as conn:
                repo_context = {
                    "connection": conn,
                    "executor": self._query_executor
                }
                repository = self._get_repository(service_path, repo_context)
                result = await service_method(repository=repository, **kwargs)
                return result                                    
        except Exception as e:
            logger.error(f"Error executing service {service_path}: {e}")
            raise 
    def _get_repository(self, service_path: str, repo_context: dict):

        parts = service_path.split('.')
        domain = parts[0]
        entity = parts[1]
        
        conn = repo_context.get("connection")
        if not conn:
            raise ValueError("Connection not provided in repository context")
        executor = repo_context.get("executor")
        if not executor:
            raise ValueError("QueryExecutor not provided in repository context")
        #implement factory later
        repo_map = {
            #the factory folder structure is domain/entity
            "shop_meta.market": "MarketRepository",
            "shop_meta.product": "ProductRepository",
            "shop_meta.collection": "CollectionRepository",
            "shop_meta.theme": "ThemeRepository",
            "ebay.app": "EbayRepository",
            "card_catalog.card": "CardReferenceRepository",
            "card_catalog.set": "SetReferenceRepository"
        }

        repo_key = f"{domain}.{entity}"
        repo_name = repo_map.get(repo_key)

        if repo_name:
            try:
                module = importlib.import_module(f"backend.repositories.{repo_key}_repository")
                repo_class = getattr(module, repo_name)
                return repo_class(conn, executor)
            except (ImportError, AttributeError) as e:
                logger.error(f"Error loading repository {repo_name}: {e}")
                raise ValueError(f"Repository {repo_name} not found: {str(e)}")
        #return default that can execute raw queries
        return repo_context
    
    @classmethod
    async def close(cls):
        """Close all resources held by the handler"""
        if cls._instance is None:
            return
            
        if cls._pool is not None:
            logger.info("Closing ApiHandler database pool")
            try:
                await cls._pool.close()
                cls._pool = None
            except Exception as e:
                logger.error(f"Error closing database pool: {e}")

        cls._instance._query_executor = None
        logger.info("ApiHandler resources closed")
    
    