from fastapi import Depends
from typing import Annotated
from backend.request_handling.QueryExecutor import QueryExecutor, AsyncQueryExecutor
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.general import get_service_manager

async def get_query_executor() -> QueryExecutor:
    from backend.main import query_executor
    """Get the global query executor instance from the application state"""
    # Return the global query_executor that was initialized in the lifespan context manager
    # This ensures we use the same connection pool throughout the application
    return query_executor

async def get_service_manager() -> ServiceManager:
    """Get the ServiceManager instance from global application state"""
    from backend.main import service_manager
    if service_manager is None:
        raise RuntimeError("ServiceManager not initialized")
    return service_manager
