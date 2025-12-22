from fastapi import Depends,  Request,Request
from typing import Annotated, Any
from backend.request_handling.QueryExecutor import QueryExecutor, AsyncQueryExecutor
from backend.new_services.service_manager import ServiceManager

# ==========================================
# Core Service Dependencies
# ==========================================

def get_query_executor(request: Request) -> QueryExecutor:
    """Get the global query executor instance from the application state"""
    return request.app.state.query_executor

def get_service_manager(request: Request) -> ServiceManager:
    """
    Get ServiceManager from app state
    ✅ No more global imports from backend.main
    """
    if not hasattr(request.app.state, 'service_manager') or request.app.state.service_manager is None:
        raise RuntimeError("ServiceManager not initialized")
    return request.app.state.service_manager


# ==========================================
# Database Pool Dependencies
# ==========================================

def get_sync_db_pool(request: Request):
    """Dependency injection for database pool"""
    return request.app.state.sync_db_pool

def get_async_db_pool(request: Request):
    """Dependency injection for async database pool"""
    return request.app.state.async_db_pool

# ==========================================
# Type Aliases for Cleaner Route Signatures
# ==========================================

ServiceManagerDep = Annotated[ServiceManager, Depends(get_service_manager)]
QueryExecutorDep = Annotated[AsyncQueryExecutor, Depends(get_query_executor)]
SyncPoolDep = Annotated[Any, Depends(get_sync_db_pool)]
AsyncPoolDep = Annotated[Any, Depends(get_async_db_pool)]

