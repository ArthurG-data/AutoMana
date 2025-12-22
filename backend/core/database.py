import logging, os,asyncpg
from psycopg2.extras import RealDictCursor, register_uuid, register_uuid
from psycopg2 import pool

from backend.core.settings import get_settings

logger = logging.getLogger(__name__)
register_uuid()

#change to just url later
async def init_async_pool() -> asyncpg.Pool:
    """
    Create asyncpg connection pool
    Called once during app startup in lifespan
    """
    settings = get_settings()
    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    
    logger.info("Creating async database pool")
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=60,
        server_settings={'client_encoding': 'UTF8'}
    )
    logger.info("✅ Async pool created")
    return pool

def init_sync_pool() -> pool.SimpleConnectionPool:
    settings = get_settings()
    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    """Initialize the synchronous connection pool"""
    sync_db_pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,  # Adjust based on your app's load
        dsn=dsn,
        cursor_factory=RealDictCursor,
        options='-c client_encoding=UTF8'
    )
    return sync_db_pool


async def close_async_pool(pool: asyncpg.Pool) -> None:
    """Close async pool gracefully"""
    if pool:
        await pool.close()
        logger.info("✅ Async pool closed")


def close_sync_pool(pool: pool.SimpleConnectionPool) -> None:
    """Close sync pool gracefully"""
    if pool:
        pool.closeall()
        logger.info("✅ Sync pool closed")