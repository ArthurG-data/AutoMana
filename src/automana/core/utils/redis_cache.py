import logging
from typing import Any, Optional

import orjson
from redis.asyncio import Redis
from redis.exceptions import RedisError

from automana.core.settings import get_settings

logger = logging.getLogger(__name__)

_redis_client: Optional[Redis] = None


async def get_redis_client() -> Redis:
    """Get or create async Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(settings.redis_cache_url, decode_responses=False)
    return _redis_client


async def get_from_cache(cache_key: str) -> Optional[Any]:
    """
    Retrieve value from cache. Returns None on cache miss or error.
    Errors are logged but not raised (graceful degradation).
    """
    try:
        redis_client = await get_redis_client()
        cached_bytes = await redis_client.get(cache_key)
        if cached_bytes is None:
            return None
        return orjson.loads(cached_bytes)
    except RedisError as e:
        logger.warning("cache_read_error", extra={"cache_key": cache_key, "error": str(e)})
        return None
    except Exception as e:
        logger.error("cache_deserialization_error", extra={"cache_key": cache_key, "error": str(e)})
        return None


async def set_to_cache(cache_key: str, value: Any, expiry_seconds: int = 3600) -> bool:
    """
    Store value in cache with TTL. Returns True on success, False on error.
    Errors are logged but not raised (no-op on failure).
    """
    try:
        redis_client = await get_redis_client()
        serialized = orjson.dumps(value)
        await redis_client.setex(cache_key, expiry_seconds, serialized)
        return True
    except RedisError as e:
        logger.warning("cache_write_error", extra={"cache_key": cache_key, "error": str(e)})
        return False
    except Exception as e:
        logger.error("cache_serialization_error", extra={"cache_key": cache_key, "error": str(e)})
        return False


async def invalidate_cache_pattern(pattern: str) -> int:
    """
    Delete all keys matching pattern. Returns count of deleted keys.
    Used for cache invalidation (e.g., "card_search:*").
    """
    try:
        redis_client = await get_redis_client()
        cursor = 0
        deleted_count = 0
        async for key in redis_client.scan_iter(match=pattern):
            await redis_client.delete(key)
            deleted_count += 1
        return deleted_count
    except RedisError as e:
        logger.warning("cache_invalidation_error", extra={"pattern": pattern, "error": str(e)})
        return 0