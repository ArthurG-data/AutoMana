import asyncio, logging ,os, asyncpg
from psycopg2.extras import RealDictCursor, register_uuid, register_uuid
from psycopg2 import pool

from backend.core.settings import Settings

logger = logging.getLogger(__name__)
register_uuid()


def _compute_backoff_seconds(attempt: int, base_delay: float, max_delay: float) -> float:
    # attempt is 1-indexed
    delay = base_delay * (2 ** max(0, attempt - 1))
    return min(delay, max_delay)

async def init_async_pool(settings:Settings) -> asyncpg.Pool:
    """
    Create asyncpg connection pool
    Called once during app startup in lifespan
    """
    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    max_attempts = settings.DB_CONNECT_MAX_ATTEMPTS
    base_delay = settings.DB_CONNECT_BASE_DELAY_SECONDS
    max_delay = settings.DB_CONNECT_MAX_DELAY_SECONDS

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Creating async database pool (attempt %s/%s)", attempt, max_attempts)
            async_pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=2,
                max_size=10,
                command_timeout=60,
                server_settings={"client_encoding": "UTF8"},
            )
            logger.info("✅ Async pool created")
            return async_pool
        except Exception as exc:  # asyncpg raises a variety of network/PG exceptions
            last_exc = exc
            if attempt >= max_attempts:
                break

            delay = _compute_backoff_seconds(attempt, base_delay, max_delay)
            logger.warning(
                "Async DB pool creation failed (attempt %s/%s): %s. Retrying in %.2fs",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("Failed to create async DB pool after retries") from last_exc

def init_sync_pool(settings: Settings) -> pool.SimpleConnectionPool:
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


async def init_sync_pool_with_retry(settings: Settings) -> pool.SimpleConnectionPool:
    """Initialize the sync psycopg2 pool with retry/backoff.

    Runs the blocking pool creation in a worker thread to avoid blocking the event loop.
    """
    max_attempts = settings.DB_CONNECT_MAX_ATTEMPTS
    base_delay = settings.DB_CONNECT_BASE_DELAY_SECONDS
    max_delay = settings.DB_CONNECT_MAX_DELAY_SECONDS

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Creating sync database pool (attempt %s/%s)", attempt, max_attempts)
            sync_pool = await asyncio.to_thread(init_sync_pool, settings)
            logger.info("✅ Sync pool created")
            return sync_pool
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break

            delay = _compute_backoff_seconds(attempt, base_delay, max_delay)
            logger.warning(
                "Sync DB pool creation failed (attempt %s/%s): %s. Retrying in %.2fs",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("Failed to create sync DB pool after retries") from last_exc


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