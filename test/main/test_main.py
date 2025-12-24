# test/main/test_main.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio
from contextlib import AsyncExitStack
from fastapi import FastAPI

from backend.main import lifespan, global_cleanup
from backend.core.service_manager import ServiceManager
from backend.request_handling.QueryExecutor import AsyncQueryExecutor

@pytest.fixture
def mock_app():
    """Mock the FastAPI app for testing"""
    return FastAPI()

@pytest.fixture
def mock_db_pool():
    """Create a mock database pool"""
    pool = AsyncMock()
    
    # Make sure close method returns a coroutine
    async def mock_close():
        return None
    pool.close = mock_close
    
    return pool

@pytest.fixture
def mock_query_executor(mock_db_pool):
    """Create a mock query executor"""
    executor = MagicMock(spec=AsyncQueryExecutor)
    executor.pool = mock_db_pool
    return executor



@pytest.mark.asyncio
@patch("backend.main.init_async_pool")
@patch.object(ServiceManager, "initialize")
@patch.object(ServiceManager, "close")
async def test_lifespan_success(mock_service_close, mock_service_init, mock_init_pool, mock_app, mock_db_pool, mock_query_executor):
    """Test successful startup and shutdown of lifespan"""
    # Setup mocks
    mock_init_pool.return_value = mock_db_pool
    
    # Mock the query executor creation
    with patch("backend.main.AsyncQueryExecutor", return_value=mock_query_executor):
        # Use AsyncExitStack to test the async context manager
        async with AsyncExitStack() as stack:
            # Enter the lifespan context
            cm = lifespan(mock_app)
            await stack.enter_async_context(cm)
            
            # Verify initialization
            mock_init_pool.assert_called_once()
            mock_service_init.assert_called_once()
            
            # Check globals are set
            from backend.main import db_pool, query_executor, error_handler
            assert db_pool is not None
            assert query_executor is not None
            assert error_handler is not None
        
        # After context exit, verify cleanup
        mock_service_close.assert_called_once()
        mock_db_pool.close.assert_awaited_once()
        
        # Check globals are cleaned up
        from backend.main import db_pool, query_executor, error_handler
        assert db_pool is None
        assert query_executor is None
        assert error_handler is None


"""
@pytest.mark.asyncio
def test_main_root_success():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the AutoMana API!"}

@pytest.mark.asyncio
def test_main_root_not_found():
    response = client.get("/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
"""
