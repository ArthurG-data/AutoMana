import pytest
from fastapi import HTTPException
from backend.request_handling.ErrorHandler import Psycopg2ExceptionHandler, AsyncpgExceptionHandler


@pytest.fixture
def psycopg2_handler():
    """Fixture for Psycopg2ExceptionHandler"""
    return Psycopg2ExceptionHandler()

@pytest.fixture
def asyncpg_handler():
    """Fixture for AsyncpgExceptionHandler"""
    return AsyncpgExceptionHandler()

def test_psycopg2_unique_violation_success(psycopg2_handler):
    """Test handling of UniqueViolation exception"""
    from psycopg2.errors import UniqueViolation
    with pytest.raises(HTTPException) as exc_info:
        psycopg2_handler.handle(UniqueViolation("Duplicate entry"))
    assert exc_info.value.status_code == 409
    assert str(exc_info.value.detail) == "Conflict: Duplicate entry."

def test_asyncpg_handle_success(asyncpg_handler):
    """Test handling of asyncpg exceptions"""
    with pytest.raises(HTTPException) as exc_info:
        asyncpg_handler.handle(Exception("Sync handle called on async handler"))
    assert exc_info.value.status_code == 500
    assert str(exc_info.value.detail) == "Handler mis-used in sync context."

def test_psycopg2_foreign_key_violation_success(psycopg2_handler):
    """Test handling of ForeignKeyViolation exception"""
    from psycopg2.errors import ForeignKeyViolation
    with pytest.raises(HTTPException) as exc_info:
        psycopg2_handler.handle(ForeignKeyViolation("Related record missing"))
    assert exc_info.value.status_code == 409
    assert str(exc_info.value.detail) == "Conflict: Related record missing."

def test_psycopg2_data_error_success(psycopg2_handler):
    """Test handling of DataError exception"""
    from psycopg2 import DataError
    with pytest.raises(HTTPException) as exc_info:
        psycopg2_handler.handle(DataError("Invalid data"))
    assert exc_info.value.status_code == 400
    assert str(exc_info.value.detail) == "Invalid data: Invalid data"

def test_psycopg2_operational_error_success(psycopg2_handler):
    """Test handling of OperationalError exception"""
    from psycopg2 import OperationalError
    with pytest.raises(HTTPException) as exc_info:
        psycopg2_handler.handle(OperationalError("DB unavailable"))
    assert exc_info.value.status_code == 503
    assert str(exc_info.value.detail) == "Database temporarily unavailable."

def test_psycopg2_database_error_success(psycopg2_handler):
    """Test handling of DatabaseError exception"""
    from psycopg2 import DatabaseError
    with pytest.raises(HTTPException) as exc_info:
        psycopg2_handler.handle(DatabaseError("Internal DB error"))
    assert exc_info.value.status_code == 500
    assert str(exc_info.value.detail) == "Internal database error."

def test_psycopg2_unexpected_error_success(psycopg2_handler):
    """Test handling of unexpected exceptions"""
    with pytest.raises(HTTPException) as exc_info:
        psycopg2_handler.handle(Exception("Unexpected error"))
    assert exc_info.value.status_code == 500
    assert str(exc_info.value.detail) == "Unexpected server error."

@pytest.mark.asyncio
async def test_psycopg2_handles_async_success(psycopg2_handler):
    """Test that async handling calls sync handler"""
    from psycopg2.errors import UniqueViolation
    with pytest.raises(HTTPException) as exc_info:
        await psycopg2_handler.handle_async(UniqueViolation("Conflict: Duplicate entry."))
    assert exc_info.value.status_code == 409
    assert str(exc_info.value.detail) == "Conflict: Duplicate entry."

def test_asyncpg_handle_success(asyncpg_handler):
    """Test handling of asyncpg exceptions"""
    with pytest.raises(HTTPException) as exc_info:
        asyncpg_handler.handle(Exception("Sync handle called on async handler"))
    assert exc_info.value.status_code == 500
    assert str(exc_info.value.detail) == "Handler mis-used in sync context."
