import asyncio, logging ,os, asyncpg
from psycopg2.extras import RealDictCursor, register_uuid, register_uuid
from psycopg2 import pool

from automana.core.settings import Settings

logger = logging.getLogger(__name__)
register_uuid()


# Search path pinned on every pool connection so historical repository SQL
# that still references tables unqualified (e.g. `FROM users`) resolves
# correctly after migration 15 relocated user-management objects out of
# `public`. `public` stays in the path because extension functions
# (uuid_generate_v4, gen_random_uuid, pgvector operators) live there.
# Keep the order so higher-priority schemas win on name collisions.
_SEARCH_PATH = (
    "user_management, public, card_catalog, user_collection, "
    "app_integration, pricing, markets, ops"
)


def _compute_backoff_seconds(attempt: int, base_delay: float, max_delay: float) -> float:
    # attempt is 1-indexed
    delay = base_delay * (2 ** max(0, attempt - 1))
    return min(delay, max_delay)

async def init_async_pool(settings:Settings) -> asyncpg.Pool:
    """
    Create asyncpg connection pool
    Called once during app startup in lifespan
    """
    dsn = settings.DATABASE_URL_ASYNC

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
                server_settings={
                    "client_encoding": "UTF8",
                    "search_path": _SEARCH_PATH,
                    # Pre-set temp_buffers to the value that
                    # pricing.load_staging_prices_batched requests via
                    # SET LOCAL.  PostgreSQL only blocks changes to
                    # temp_buffers after the first temp-table access in a
                    # session; if the connection already holds the target
                    # value the SET LOCAL becomes a no-op and the check
                    # passes even on a recycled pool connection that has
                    # previously run the procedure.  Without this, the
                    # asyncpg pool hands back a warmed-up connection whose
                    # local buffer count is already initialised, causing:
                    #   InvalidParameterValueError: "temp_buffers" cannot be
                    #   changed after any temporary tables have been accessed.
                    "temp_buffers": "32768",  # 32768 × 8 kB = 256 MB
                },
            )
            logger.info("Async pool created")
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
    dsn = settings.DATABASE_URL_ASYNC.replace("postgresql+asyncpg://", "postgresql://")
    """Initialize the synchronous connection pool"""
    # psycopg2 passes `options` as libpq command-line options. Order and
    # spacing don't matter; each `-c key=value` sets a GUC at connection
    # start. The search_path here mirrors `_SEARCH_PATH` above — keep them
    # in sync if you edit either.
    sync_db_pool = pool.SimpleConnectionPool(
        minconn=settings.db_pool_min_conn,
        maxconn=settings.db_pool_max_conn,
        dsn=dsn,
        cursor_factory=RealDictCursor,
        options=(
            "-c client_encoding=UTF8 "
            "-c search_path=" + _SEARCH_PATH.replace(" ", "")
        ),
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
            logger.info("Sync pool created")
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
        logger.info("Async pool closed")


def close_sync_pool(pool: pool.SimpleConnectionPool) -> None:
    """Close sync pool gracefully"""
    if pool:
        pool.closeall()
        logger.info("Sync pool closed")
