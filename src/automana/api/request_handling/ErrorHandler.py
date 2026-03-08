import logging
from fastapi import HTTPException
from psycopg2 import Error as Psycopg2Error, OperationalError, DataError, DatabaseError
from psycopg2.errors import UniqueViolation, ForeignKeyViolation
import asyncpg

logger = logging.getLogger(__name__)


from typing import Protocol, runtime_checkable

@runtime_checkable
class ExceptionHandler(Protocol):
    """
    Defines the interface for handling exceptions.
    """

    def handle(self, exc: Exception) -> None:
        """
        Handle a synchronous exception (e.g. from psycopg2).
        Should raise an HTTPException or re-raise as needed.
        """
        ...

    async def handle_async(self, exc: Exception) -> None:
        """
        Handle an asynchronous exception (e.g. from asyncpg).
        Defaults to calling the sync handle() if not overridden.
        """
        ...

class Psycopg2ExceptionHandler(ExceptionHandler):
    def handle(self, exc: Exception) -> None:
        if isinstance(exc, UniqueViolation):
            raise HTTPException(409, "Conflict: Duplicate entry.")
        if isinstance(exc, ForeignKeyViolation):
            raise HTTPException(409, "Conflict: Related record missing.")
        if isinstance(exc, DataError):
            raise HTTPException(400, f"Invalid data: {str(exc).splitlines()[0]}")
        if isinstance(exc, OperationalError):
            logger.error("DB unavailable", exc_info=True)
            raise HTTPException(503, "Database temporarily unavailable.")
        if isinstance(exc, (Psycopg2Error, DatabaseError)):
            logger.error("DB error", exc_info=True)
            raise HTTPException(500, "Internal database error.")
        # fallback
        logger.error("Unexpected error", exc_info=True)
        raise HTTPException(500, "Unexpected server error.")

    async def handle_async(self, exc: Exception) -> None:
        # by default, delegate to sync handler
        return self.handle(exc)
    
class AsyncpgExceptionHandler(ExceptionHandler):
    def handle(self, exc: Exception) -> None:
        # you could reuse same logic or raise an error
        logger.error("Sync handle called on async handler", exc_info=True)
        raise HTTPException(500, "Handler mis-used in sync context.")

    async def handle_async(self, exc: Exception) -> None:
        # map asyncpg exceptions similarly
        if isinstance(exc, asyncpg.UniqueViolationError):
            raise HTTPException(409, "Conflict: Duplicate entry.")
        if isinstance(exc, asyncpg.ForeignKeyViolationError):
            raise HTTPException(409, "Conflict: Related record missing.")
        if isinstance(exc, asyncpg.DataError):
            raise HTTPException(400, f"Invalid data: {str(exc).splitlines()[0]}")   
        # … other mappings …
        logger.error("Asyncpg error", exc_info=True)
        raise HTTPException(500, "Internal database error.")
