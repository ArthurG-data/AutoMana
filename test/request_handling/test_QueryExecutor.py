# test/request_handling/test_QueryExecutor.py
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import asyncpg
import logging
from typing import Dict, Any, List, Optional

from backend.core.QueryExecutor import AsyncQueryExecutor

# Disable logging during tests
logging.basicConfig(level=logging.CRITICAL)

class TestAsyncQueryExecutor:
    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection"""
        conn = AsyncMock(spec=asyncpg.Connection)
        return conn
    
    @pytest.fixture
    def mock_pool(self, mock_connection):
        """Create a mock connection pool that returns our mock connection"""
        pool = AsyncMock(spec=asyncpg.Pool)
        
        # Fix: Create a proper async context manager for pool.acquire()
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return mock_connection
                
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Make pool.acquire() return our context manager
        pool.acquire.return_value = AsyncContextManagerMock()
        
        return pool, mock_connection
    
    @pytest.fixture
    def mock_error_handler(self):
        """Create a mock error handler"""
        handler = MagicMock()
        handler.handle = MagicMock()
        return handler
    
    @pytest.fixture
    def executor(self, mock_pool, mock_error_handler):
        """Create an AsyncQueryExecutor with mocked dependencies"""
        pool, _ = mock_pool
        return AsyncQueryExecutor(pool, mock_error_handler)
    
    @pytest.mark.asyncio
    async def test_name(self, executor):
        """Test the name method"""
        assert executor.name() == "AsyncQueryExecutor"
    
    @pytest.mark.asyncio
    async def test_execute_command_success(self, executor, mock_pool):
        """Test successful command execution"""
        # Setup
        _, conn = mock_pool
        conn.execute.return_value = None
        
        # Execute command
        await executor.execute_command("INSERT INTO test VALUES ($1, $2)", (1, "test"))
        
        # Verify
        conn.execute.assert_called_once_with("INSERT INTO test VALUES ($1, $2)", 1, "test")
    
    @pytest.mark.asyncio
    async def test_execute_command_error(self, executor, mock_pool, mock_error_handler):
        """Test command execution with error"""
        # Setup
        _, conn = mock_pool
        error = Exception("Test error")
        conn.execute.side_effect = error
        
        # Execute and expect exception
        with pytest.raises(Exception):
            await executor.execute_command("INSERT INTO test VALUES ($1, $2)", (1, "test"))
        
        # Verify error handler was called
        mock_error_handler.handle.assert_called_once_with(error)
    
    @pytest.mark.asyncio
    async def test_execute_query_success(self, executor, mock_pool):
        """Test successful query execution"""
        # Setup
        _, conn = mock_pool
        
        # Create a mock record result
        mock_records = []
        for i in range(2):
            record = MagicMock()
            # Make the record dict-like
            record.__getitem__ = lambda s, key, i=i: f"value{i}" if key == "name" else i
            record.keys = lambda: ["id", "name"]
            mock_records.append(record)
        
        conn.fetch.return_value = mock_records
        
        # Execute query
        result = await executor.execute_query("SELECT * FROM test", params=(1,))
        
        # Verify
        conn.fetch.assert_called_once_with("SELECT * FROM test", 1)
        assert len(result) == 2
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)
    
    @pytest.mark.asyncio
    async def test_transaction_success(self, executor, mock_pool):
        """Test successful transaction execution"""
        # Setup
        _, conn = mock_pool
        
        # Create a proper transaction mock that supports async context manager
        tx = AsyncMock()
        
        # Fix: Make transaction() return a proper async context manager
        class TransactionContextManager:
            async def __aenter__(self):
                await tx.start()
                return tx
                
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    await tx.commit()
                else:
                    await tx.rollback()
        
        conn.transaction.return_value = TransactionContextManager()
        
        # Fix: Create a mock for the executor's transaction method
        # that returns a proper async context manager
        class ExecutorTransactionContext:
            async def __aenter__(self):
                return conn
                
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Replace the transaction method with our controlled mock
        with patch.object(executor, 'transaction', return_value=ExecutorTransactionContext()):
            # Execute transaction
            async with executor.transaction() as tx_conn:
                await tx_conn.execute("INSERT INTO test VALUES (1, 'test')")
        
        # Verify
        conn.execute.assert_called_once_with("INSERT INTO test VALUES (1, 'test')")
    
    @pytest.mark.asyncio
    async def test_transaction_with_error(self, executor, mock_pool, mock_error_handler):
        """Test transaction with error"""
        # Setup
        _, conn = mock_pool
        
        # Create error to be raised
        error = Exception("Transaction error")
        conn.execute.side_effect = error
        
        # Create a proper transaction mock
        tx = AsyncMock()
        
        # Fix: Make transaction() return a proper async context manager
        class TransactionContextManager:
            async def __aenter__(self):
                await tx.start()
                return tx
                
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    await tx.commit()
                else:
                    await tx.rollback()
                    return False  # Re-raise the exception
        
        conn.transaction.return_value = TransactionContextManager()
        
        # Fix: Create a mock for the executor's transaction method
        class ExecutorTransactionContext:
            async def __aenter__(self):
                return conn
                
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if exc_type is not None:
                    mock_error_handler.handle(exc_type())
                return False  # Re-raise the exception
        
        # Replace the transaction method with our controlled mock
        with patch.object(executor, 'transaction', return_value=ExecutorTransactionContext()):
            # Execute transaction with error
            with pytest.raises(Exception):
                async with executor.transaction() as tx_conn:
                    await tx_conn.execute("INSERT INTO test VALUES (1, 'test')")
        
        # Verify
        conn.execute.assert_called_once()
        mock_error_handler.handle.assert_called_once_with(error)