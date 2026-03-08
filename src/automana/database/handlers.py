from fastapi import Request
from fastapi.responses import JSONResponse
import logging
import psycopg2

logger = logging.getLogger("db")

async def psycopg_exception_handler(request: Request, exc: psycopg2.DatabaseError):
    if isinstance(exc, psycopg2.IntegrityError):
        return JSONResponse(status_code=409, content={"detail": "Conflict: Duplicate entry or constraint violation."})

    elif isinstance(exc, psycopg2.OperationalError):
        return JSONResponse(status_code=500, content={"detail": "Database connection error."})

    elif isinstance(exc, psycopg2.DataError):
        return JSONResponse(status_code=400, content={"detail": "Invalid data format."})

    elif isinstance(exc, psycopg2.ProgrammingError):
        return JSONResponse(status_code=400, content={"detail": "Invalid SQL query."})

    else:
        logger.error(f"Unhandled database error: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})
    
