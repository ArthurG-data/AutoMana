from backend.database.get_database import get_connection, get_async_pool_connection, init_async_pool
import importlib
from contextlib import asynccontextmanager
from backend.request_handling.utils import locate_service
from backend.request_handling.QueryExecutor import AsyncQueryExecutor, QueryExecutor
from backend.request_handling.ErrorHandler import Psycopg2ExceptionHandler
import logging

logger = logging.getLogger(__name__)

class ApiHandler:

    _instance = None
    _pool = None
    _error_handler : Psycopg2ExceptionHandler = None
    _query_executor : QueryExecutor = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ApiHandler, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the hanlder and other dependencies"""
        self._error_handler = Psycopg2ExceptionHandler()

    async def _ensure_pool(self):
        if ApiHandler._pool is None:
            ApiHandler._pool = await init_async_pool()
        return ApiHandler._pool

    async def _ensure_query_executor(self) -> QueryExecutor:
        if not ApiHandler._query_executor:
            pool = await self._ensure_pool()
            ApiHandler._query_executor = AsyncQueryExecutor(pool, self._error_handler)
        return ApiHandler._query_executor
        
    @classmethod
    async def execute_service(cls, service_path: str, **kwargs):
        if cls._instance is None:
            cls._instance = ApiHandler()
            await cls._instance._ensure_query_executor()
        return await cls._instance._execute_service(service_path, **kwargs)


    async def _execute_service(self, service_path: str, **kwargs):
        #get the service method 

        service_method = locate_service(service_path)
 
        #set the query executor if not set

        query_executor : QueryExecutor = await self._ensure_query_executor()

        logger.info(f"Executing service: {service_path}")
        try:
            async with query_executor.transaction() as conn:
                repo_context = {
                "connection": conn,
                "executor": query_executor
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
            module = importlib.import_module(f"backend.repositories.{repo_key}_repository")
            repo_class = getattr(module, repo_name)
            return repo_class(conn, executor)
        #return default that can execute raw queries
        return repo_context
    
    