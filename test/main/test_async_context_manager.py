import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import AsyncExitStack
from fastapi import FastAPI

from backend.main import lifespan, global_cleanup
from backend.new_services.service_manager import ServiceManager
from backend.request_handling.ErrorHandler import Psycopg2ExceptionHandler
from backend.request_handling.QueryExecutor import AsyncQueryExecutor

@pytest.fixture
def mock_app():
    """Create a mock FastAPI application"""
    return FastAPI()

@pytest.mark.asyncio
@patch("backend.main.init_async_pool")
@patch.object(ServiceManager, "initialize")
@patch.object(ServiceManager, "close")
async def test_lifespan_startup_success(mock_close, mock_initialize, mock_init_pool, mock_app):
    """Test successful startup of lifespan"""
    # Setup mocks
    mock_pool = AsyncMock()
    mock_init_pool.return_value = mock_pool
    mock_initialize.return_value = None
    
    # Create an async context manager for testing
    async with AsyncExitStack() as stack:
        # Push the lifespan context manager onto the stack
        cm = lifespan(mock_app)
        await stack.enter_async_context(cm)
        
        # Verify initialization
        mock_init_pool.assert_called_once()
        mock_initialize.assert_called_once()
        
        # Check global variables are set
        from backend.main import db_pool, query_executor, error_handler
        assert db_pool is not None
        assert query_executor is not None
        assert isinstance(error_handler, AsyncQueryExecutor)
    
    # After context exit, verify cleanup
    mock_close.assert_called_once()
    mock_pool.close.assert_called_once()
    
    # Check globals are cleaned up
    from backend.main import db_pool, query_executor, error_handler
    assert db_pool is None
    assert query_executor is None
    assert error_handler is None

@pytest.mark.asyncio
@patch("backend.main.init_async_pool")
@patch.object(ServiceManager, "initialize")
async def test_lifespan_startup_db_failure(mock_initialize, mock_init_pool, mock_app):
    """Test lifespan when database pool creation fails"""
    # Setup mocks to simulate failure
    mock_init_pool.side_effect = Exception("DB connection error")
    
    # Create an async context manager for testing
    with pytest.raises(Exception, match="DB connection error"):
        async with AsyncExitStack() as stack:
            cm = lifespan(mock_app)
            await stack.enter_async_context(cm)
    
    # Verify initialization was attempted but ServiceManager.initialize was not called
    mock_init_pool.assert_called_once()
    mock_initialize.assert_not_called()
    
    # Check globals were cleaned up
    from backend.main import db_pool, query_executor
    assert db_pool is None
    assert query_executor is None