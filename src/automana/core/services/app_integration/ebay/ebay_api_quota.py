"""Redis-backed daily API call quota guard shared across eBay Finding API tasks.

Tracks one unit per fetched page (each page = one eBay API call).
Key: ebay:api_calls:{YYYY-MM-DD}, expires after 24 h.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_QUOTA_KEY_PREFIX = "ebay:api_calls"
_KEY_TTL_SECONDS = 86_400


def _key(today: str) -> str:
    return f"{_QUOTA_KEY_PREFIX}:{today}"


async def quota_remaining(redis_client, today: str, limit: int) -> int:
    """Return how many API calls remain for today (0 = exhausted)."""
    raw = await redis_client.get(_key(today))
    used = int(raw) if raw else 0
    return max(0, limit - used)


async def quota_increment(redis_client, today: str) -> int:
    """Increment daily call counter. Returns new count. Sets TTL on first use."""
    key = _key(today)
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, _KEY_TTL_SECONDS)
    return count
