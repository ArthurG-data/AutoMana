from backend.database.get_database import get_connection, get_async_pool_connection, init_async_pool
import importlib
from contextlib import asynccontextmanager
from backend.request_handling.utils import locate_service
from backend.request_handling.QueryExecutor import AsyncQueryExecutor
import logging

logger = logging.getLogger(__name__)

class ApiHandler:

    _instance = None
    _pool = None

    def _new__(cls):
        if cls._instance is None:
            cls._instance = super(ApiHandler, cls).__new__(cls)
        return cls._instance
    
    async def _ensure_pool(self):
        if ApiHandler._pool is None:
            ApiHandler._pool = await init_async_pool()
        return ApiHandler._pool
    
    async def execute_service(self, service_path: str, **kwargs):
        #get the service method 

        service_method = locate_service(service_path)
        #get pool
        pool = await self._ensure_pool()
        executor = AsyncQueryExecutor(pool)
    
        logger.info(f"Executing service: {service_path}")
        async with pool.acquire() as conn:
            try:
                async with executor.transaction() as conn:
                    repository = self._get_repository(service_path, conn)
                    result = await service_method(repository=repository, **kwargs)

                    return result

                                                        
            except Exception as e:
                logger.error(f"Error executing service {service_path}: {e}")
                raise 
    def _get_repository(self, service_path: str, conn):

        domain = service_path.split('.')[0]

        repo_map = {
            "shop_meta": "ShopMetadataRepository",
            "ebay": "EbayRepository",
            "card": "CardRepository"
        }

        repo_name = repo_map.get(domain)
        if repo_name:
            module = importlib.import_module(f"backend.repositories.{domain}_repository")
            repo_class = getattr(module, repo_name)
            return repo_class(conn)
        #return default that can execute raw queries
        return conn
    