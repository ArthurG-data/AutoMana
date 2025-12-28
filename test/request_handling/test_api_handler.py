# test/request_handling/test_async_query_executor.py
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
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
        
        # Setup mock methods
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock()
        conn.close = AsyncMock()
        conn.transaction = AsyncMock()
        
        return conn
    
    @pytest.fixture
    def mock_pool(self, mock_connection):
        """Create a mock connection pool that returns our mock connection"""
        pool = AsyncMock(spec=asyncpg.Pool)
        
        # Make pool.acquire() return our mock connection
        pool.acquire = AsyncMock(return_value=mock_connection)
        
        # Make context manager version work too
        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_connection)
        async_cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire.return_value = mock_connection
        
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
        conn.execute.assert_awaited_once_with("INSERT INTO test VALUES ($1, $2)", 1, "test")
    
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
        conn.fetch.assert_awaited_once_with("SELECT * FROM test", 1)
        assert len(result) == 2
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)
    
    @pytest.mark.asyncio
    async def test_execute_query_with_mapper(self, executor, mock_pool):
        """Test query execution with mapper function"""
        # Setup
        _, conn = mock_pool
        
        # Create a mock record that can be unpacked as multiple arguments
        class MockRecord(list):
            def __iter__(self):
                yield 1  # id
                yield "test"  # name
        
        conn.fetch.return_value = [MockRecord(), MockRecord()]
        
        # Define mapper function
        def mapper(id, name):
            return {"mapped_id": id, "mapped_name": name}
        
        # Execute query with mapper
        result = await executor.execute_query(
            "SELECT * FROM test", 
            params=(1,), 
            mapper=mapper
        )
        
        # Verify
        assert len(result) == 2
        assert result[0]["mapped_id"] == 1
        assert result[0]["mapped_name"] == "test"
    
    @pytest.mark.asyncio
    async def test_execute_query_error(self, executor, mock_pool, mock_error_handler):
        """Test query execution with error"""
        # Setup
        _, conn = mock_pool
        error = Exception("Query error")
        conn.fetch.side_effect = error
        
        # Execute and expect exception
        with pytest.raises(Exception):
            await executor.execute_query("SELECT * FROM test", params=(1,))
        
        # Verify error handler was called
        mock_error_handler.handle.assert_called_once_with(error)
    
    @pytest.mark.asyncio
    async def test_transaction_success(self, executor, mock_pool):
        """Test successful transaction execution"""
        # Setup
        _, conn = mock_pool
        tx = AsyncMock()
        conn.transaction.return_value = tx
        
        # Simulate successful transaction
        tx.__aenter__ = AsyncMock(return_value=tx)
        tx.__aexit__ = AsyncMock(return_value=None)
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        tx.rollback = AsyncMock()
        
        # Execute transaction
        async with executor.transaction() as tx_conn:
            await tx_conn.execute("INSERT INTO test VALUES (1, 'test')")
        
        # Verify
        tx.start.assert_awaited_once()
        conn.execute.assert_awaited_once_with("INSERT INTO test VALUES (1, 'test')")
        tx.commit.assert_awaited_once()
        tx.rollback.assert_not_awaited()
    
    @pytest.mark.asyncio
    async def test_transaction_with_error(self, executor, mock_pool, mock_error_handler):
        """Test transaction with error"""
        # Setup
        _, conn = mock_pool
        tx = AsyncMock()
        conn.transaction.return_value = tx
        
        # Simulate transaction
        tx.__aenter__ = AsyncMock(return_value=tx)
        tx.__aexit__ = AsyncMock(return_value=None)
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        tx.rollback = AsyncMock()
        
        # Make execute raise an error
        error = Exception("Transaction error")
        conn.execute.side_effect = error
        
        # Execute transaction with error
        with pytest.raises(Exception):
            async with executor.transaction() as tx_conn:
                await tx_conn.execute("INSERT INTO test VALUES (1, 'test')")
        
        # Verify
        tx.start.assert_awaited_once()
        conn.execute.assert_awaited_once()
        tx.commit.assert_not_awaited()
        tx.rollback.assert_awaited_once()
        mock_error_handler.handle.assert_called_once_with(error)