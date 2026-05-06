# Cache Infrastructure Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from synchronous blocking Redis to async Redis, implement missing price history cache, add error handling to cache utilities, move config to settings.py, and clean up dead code.

**Architecture:** The cache layer sits between services and Redis. Currently it uses blocking redis.Redis which serializes all cache access behind the event loop. Migration to redis.asyncio.Redis requires async/await throughout the call chain (services, auth_context). Error handling applies graceful degradation: cache misses on read errors, no-op on write errors. Config moves from `os.getenv` to Pydantic Settings. Price history caching follows the same pattern as card search caching.

**Tech Stack:** redis.asyncio.Redis, Pydantic v2, orjson, pytest with pytest-asyncio

---

## File Structure

**Core Infrastructure:**
- `core/settings.py` - add REDIS_CACHE_URL
- `core/utils/redis_cache.py` - async client, error handling, single serialization

**Service Layer (consumers of cache):**
- `services/card_catalog/card_service.py` - await cache calls, implement price history cache, fix triple-encode
- `services/auth_services.py` - await cache calls, error handling
- `services/app_integration/ebay/_auth_context.py` - await cache calls
- `services/app_integration/ebay/browsing_services.py` - fix import, wire in search cache
- `services/app_integration/ebay/cache.py` - delete (dead code)
- `services/app_integration/ebay/response_utils.py` - remove print statement
- `services/card_catalog/card_service.py` - remove print statement

**Tests:**
- `tests/unit/core/test_redis_cache.py` - async cache behavior, error handling
- `tests/integration/services/test_card_search_cache.py` - existing tests + new async behavior
- `tests/integration/services/test_price_cache.py` - new price history cache tests

---

## Phase 1: Core Cache Infrastructure

### Task 1: Add REDIS_CACHE_URL to Settings

**Files:**
- Modify: `core/settings.py`

- [ ] **Step 1: Read current settings structure**

Run: `grep -A 20 "class Settings" /home/arthur/projects/AutoMana/src/automana/core/settings.py`

Understand the pattern for URL fields (look for existing Redis/broker config).

- [ ] **Step 2: Add REDIS_CACHE_URL field**

In `core/settings.py`, after the BROKER_URL or similar config, add:

```python
redis_cache_url: str = Field(
    default="redis://localhost:6379/1",
    validation_alias="REDIS_CACHE_URL",
    description="Redis URL for cache operations (separate from Celery broker)"
)
```

- [ ] **Step 3: Verify settings load correctly**

Run: `cd /home/arthur/projects/AutoMana && python -c "from automana.core.settings import get_settings; s = get_settings(); print(f'Cache URL: {s.redis_cache_url}')"` 

Expected: Prints cache URL (default or from env)

- [ ] **Step 4: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add src/automana/core/settings.py
git commit -m "config: add REDIS_CACHE_URL to Settings"
```

---

### Task 2: Migrate redis_cache.py to Async Redis with Error Handling

**Files:**
- Modify: `core/utils/redis_cache.py`

- [ ] **Step 1: Read current implementation**

Run: `cat /home/arthur/projects/AutoMana/src/automana/core/utils/redis_cache.py`

Note the current sync client, cache functions, and key generation.

- [ ] **Step 2: Replace with async implementation**

Replace the entire file with:

```python
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
```

- [ ] **Step 3: Run type checker to catch import issues**

Run: `cd /home/arthur/projects/AutoMana && python -m mypy src/automana/core/utils/redis_cache.py --no-error-summary 2>&1 | head -20`

Fix any import or type issues. Expected: Either clean or fixable type hints.

- [ ] **Step 4: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add src/automana/core/utils/redis_cache.py
git commit -m "refactor: migrate redis_cache to async Redis with error handling"
```

---

### Task 3: Update card_service.py to Use Async Cache

**Files:**
- Modify: `services/card_catalog/card_service.py:159-230` (search_cards function)

- [ ] **Step 1: Read search_cards function**

Run: `sed -n '159,230p' /home/arthur/projects/AutoMana/src/automana/services/card_catalog/card_service.py`

Note the current cache calls, parameters, and result structure.

- [ ] **Step 2: Add async imports and update function signature**

At the top of the function where imports are, verify `redis_cache` is imported. The function `search_cards` should already be async. Verify with:

```bash
grep -n "async def search_cards" /home/arthur/projects/AutoMana/src/automana/services/card_catalog/card_service.py
```

- [ ] **Step 3: Update cache read to await**

Find the line `cache_result = get_from_cache(cache_key)` (around line 183) and replace with:

```python
cache_result = await get_from_cache(cache_key)
```

- [ ] **Step 4: Update cache write to await**

Find the line `set_to_cache(cache_key, cache_data, ...)` (around line 222) and replace with:

```python
await set_to_cache(cache_key, cache_data, expiry_seconds=3600)
```

- [ ] **Step 5: Remove triple-encode inefficiency**

Find lines 221-226 (the cache data preparation):

```python
cache_data = {"cards": [c.model_dump() for c in result.cards], "total_count": result.total_count}
set_to_cache(
    cache_key,
    json.loads(BaseCard.to_json_safe(cache_data)),
    expiry_seconds=3600,
)
```

Replace with:

```python
cache_data = {
    "cards": [c.model_dump(mode="json") for c in result.cards],
    "total_count": result.total_count
}
await set_to_cache(cache_key, cache_data, expiry_seconds=3600)
```

- [ ] **Step 6: Remove print statement at line 212**

Find and delete: `print(file_exist)`

Replace with nothing (entire line deletion).

- [ ] **Step 7: Update suggest_cards cache calls**

Find `suggest_cards` function (around line 245). Update:
- `get_from_cache(...)` → `await get_from_cache(...)`
- `set_to_cache(...)` → `await set_to_cache(...)`

- [ ] **Step 8: Run linter on card_service.py**

Run: `cd /home/arthur/projects/AutoMana && python -m pylint src/automana/services/card_catalog/card_service.py --disable=all --enable=E,F 2>&1 | head -30`

Fix any syntax errors. Expected: No errors.

- [ ] **Step 9: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add src/automana/services/card_catalog/card_service.py
git commit -m "refactor: await async cache calls in card_service, remove triple-encode"
```

---

### Task 4: Update auth_services.py to Use Async Cache

**Files:**
- Modify: `services/auth_services.py:147-151, 219-223`

- [ ] **Step 1: Find eBay token cache calls**

Run: `grep -n "setex\|get_from_cache" /home/arthur/projects/AutoMana/src/automana/services/auth_services.py`

Note the line numbers for both calls.

- [ ] **Step 2: Add async/await to eBay OAuth token storage**

Find the line around 148: `redis_client.setex(...)` 

This needs to become an `await` call to the new async cache utility. Replace:

```python
redis_client.setex(...)
```

with:

```python
cache_key = f"ebay:access_token:{user_id}:{app_code}"
await set_to_cache(cache_key, {"access_token": token, "expires_in": expires_in}, expiry_seconds=expires_in - 60)
```

(Adjust variable names to match the actual function context.)

- [ ] **Step 3: Add async/await to eBay token refresh**

Find the line around 220 with similar `setex` call and apply the same transformation.

- [ ] **Step 4: Import async cache utility at top**

Add to imports: `from automana.core.utils.redis_cache import get_from_cache, set_to_cache`

Remove any direct `redis_client` imports that are no longer needed.

- [ ] **Step 5: Verify function is async**

Run: `grep -B 2 "def.*token" /home/arthur/projects/AutoMana/src/automana/services/auth_services.py | head -10`

Both functions storing tokens should be `async def`.

- [ ] **Step 6: Run linter**

Run: `cd /home/arthur/projects/AutoMana && python -m pylint src/automana/services/auth_services.py --disable=all --enable=E,F 2>&1 | head -20`

Expected: No errors.

- [ ] **Step 7: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add src/automana/services/auth_services.py
git commit -m "refactor: await async cache calls in auth_services"
```

---

### Task 5: Update _auth_context.py to Use Async Cache

**Files:**
- Modify: `services/app_integration/ebay/_auth_context.py:50, 104-108`

- [ ] **Step 1: Find token retrieval and storage**

Run: `grep -n "redis_client\|get_from_cache" /home/arthur/projects/AutoMana/src/automana/services/app_integration/ebay/_auth_context.py`

Note all cache-related lines.

- [ ] **Step 2: Replace cache retrieval at line 50**

Find: `redis_client.get(cache_key)` 

Replace with: `await get_from_cache(cache_key)`

- [ ] **Step 3: Replace cache storage at lines 104-108**

Find: `redis_client.setex(...)` 

Replace with: `await set_to_cache(cache_key, token_data, expiry_seconds=...)`

- [ ] **Step 4: Ensure function is async**

Run: `grep -B 3 "def.*get_ebay_token\|def.*refresh" /home/arthur/projects/AutoMana/src/automana/services/app_integration/ebay/_auth_context.py | head -10`

Functions accessing cache must be `async def`.

- [ ] **Step 5: Add imports**

At top of file, add: `from automana.core.utils.redis_cache import get_from_cache, set_to_cache`

Remove any direct `redis_client` imports.

- [ ] **Step 6: Run linter**

Run: `cd /home/arthur/projects/AutoMana && python -m pylint src/automana/services/app_integration/ebay/_auth_context.py --disable=all --enable=E,F 2>&1 | head -20`

Expected: No errors.

- [ ] **Step 7: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add src/automana/services/app_integration/ebay/_auth_context.py
git commit -m "refactor: await async cache calls in _auth_context"
```

---

## Phase 2: Implement Missing Caches

### Task 6: Implement Price History Caching

**Files:**
- Modify: `services/card_catalog/card_service.py:260-306` (get_card_price_history function)
- Modify: `api/routers/mtg/card_reference.py:132-133` (docstring)

- [ ] **Step 1: Read price history function**

Run: `sed -n '260,306p' /home/arthur/projects/AutoMana/src/automana/services/card_catalog/card_service.py`

Note the parameters: `card_id`, `finish`, and the database queries.

- [ ] **Step 2: Add cache key generation**

At the start of `get_card_price_history`, add:

```python
cache_key = f"price_history:{card_id}:{finish}"
cached_result = await get_from_cache(cache_key)
if cached_result is not None:
    logger.debug("price_cache_hit", extra={"card_id": str(card_id), "finish": finish})
    return PriceHistoryResult(**cached_result)  # or appropriate reconstruction
```

(Adjust the result type to match the actual return type of the function.)

- [ ] **Step 3: Add cache write at end of function**

Before the return statement, add:

```python
result_dict = result.model_dump(mode="json") if hasattr(result, 'model_dump') else result
await set_to_cache(cache_key, result_dict, expiry_seconds=86400)  # 24 hour TTL
```

- [ ] **Step 4: Update router docstring**

The docstring is already correct ("Responses are cached for 24 hours"). Verify it at `card_reference.py:132-133`.

Run: `sed -n '132,133p' /home/arthur/projects/AutoMana/src/automana/api/routers/mtg/card_reference.py`

No change needed if it already says "cached for 24 hours".

- [ ] **Step 5: Verify function is async**

Run: `grep "async def get_card_price_history" /home/arthur/projects/AutoMana/src/automana/services/card_catalog/card_service.py`

Should return a match. If not, add `async` to the function signature.

- [ ] **Step 6: Run linter on modified file**

Run: `cd /home/arthur/projects/AutoMana && python -m pylint src/automana/services/card_catalog/card_service.py --disable=all --enable=E,F 2>&1 | head -20`

Expected: No errors.

- [ ] **Step 7: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add src/automana/services/card_catalog/card_service.py
git commit -m "feat: implement 24-hour cache for price history"
```

---

## Phase 3: Code Cleanup

### Task 7: Remove Dead eBay Cache Module

**Files:**
- Delete: `services/app_integration/ebay/cache.py`
- Modify: `services/app_integration/ebay/browsing_services.py:2, 55-105`

- [ ] **Step 1: Verify cache.py is unused**

Run: `grep -r "from.*ebay.cache import\|from.*cache import" /home/arthur/projects/AutoMana/src/automana --include="*.py" | grep -v __pycache__`

Expected: No results (dead code).

- [ ] **Step 2: Check browsing_services.py imports**

Run: `sed -n '1,10p' /home/arthur/projects/AutoMana/src/automana/services/app_integration/ebay/browsing_services.py`

Look for the broken `from fastapi import requests` import.

- [ ] **Step 3: Fix broken import**

Remove or comment out: `from fastapi import requests`

The correct import (if needed) should be: `import requests` (from the requests library).

However, check if `requests` is actually used. Run: `grep "requests\." /home/arthur/projects/AutoMana/src/automana/services/app_integration/ebay/browsing_services.py`

If no matches, remove the import entirely.

- [ ] **Step 4: Delete the dead cache.py file**

Run: `rm /home/arthur/projects/AutoMana/src/automana/services/app_integration/ebay/cache.py`

- [ ] **Step 5: Run linter on browsing_services.py**

Run: `cd /home/arthur/projects/AutoMana && python -m pylint src/automana/services/app_integration/ebay/browsing_services.py --disable=all --enable=E,F 2>&1 | head -20`

Expected: No import errors.

- [ ] **Step 6: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add -u src/automana/services/app_integration/ebay/
git commit -m "refactor: remove dead eBay cache module and fix broken import"
```

---

### Task 8: Remove Debug Print Statements

**Files:**
- Modify: `services/card_catalog/card_service.py:512` (print(file_exist))
- Modify: `services/app_integration/ebay/response_utils.py:58` (print f-string)

- [ ] **Step 1: Find and remove print in card_service.py**

Run: `grep -n "print(" /home/arthur/projects/AutoMana/src/automana/services/card_catalog/card_service.py`

Locate the line with `print(file_exist)` (around line 512).

- [ ] **Step 2: Replace with logger.debug**

Replace: `print(file_exist)`

With: `logger.debug("file_check", extra={"file_exist": file_exist})`

- [ ] **Step 3: Find and remove print in response_utils.py**

Run: `grep -n "print(" /home/arthur/projects/AutoMana/src/automana/services/app_integration/ebay/response_utils.py`

Locate the line with `print(f"Error parsing item: ...")` (around line 58).

- [ ] **Step 4: Replace with logger.error**

Replace: `print(f"Error parsing item: {item_id}")`

With: `logger.error("item_parse_error", extra={"item_id": item_id})`

(Adjust parameter names to match actual context.)

- [ ] **Step 5: Run linter on both files**

Run: `cd /home/arthur/projects/AutoMana && python -m pylint src/automana/services/card_catalog/card_service.py src/automana/services/app_integration/ebay/response_utils.py --disable=all --enable=E,F 2>&1 | head -20`

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add src/automana/services/card_catalog/card_service.py src/automana/services/app_integration/ebay/response_utils.py
git commit -m "refactor: replace print statements with structured logging"
```

---

### Task 9: Remove Unreachable Exception Branch

**Files:**
- Modify: `services/card_catalog/card_service.py:212-213, 229`

- [ ] **Step 1: Read the problematic code**

Run: `sed -n '210,230p' /home/arthur/projects/AutoMana/src/automana/services/card_catalog/card_service.py`

Note the `if not raw:` check and the related exception handling.

- [ ] **Step 2: Verify the check is unreachable**

Confirm that `card_repository.search()` always returns a dict (from `card_repository.py:314`).

Run: `sed -n '314,320p' /home/arthur/projects/AutoMana/src/automana/services/card_catalog/card_repository.py`

Expected: Returns `{"cards": [...], "total_count": int}` — always truthy.

- [ ] **Step 3: Remove dead code**

Delete lines 212-213:

```python
if not raw:
    raise card_exception.CardNotFoundError(f"No cards found for IDs {card_id}")
```

Also delete the related `except CardNotFoundError:` handler (around line 229) if it's only there for this branch.

- [ ] **Step 4: Run linter**

Run: `cd /home/arthur/projects/AutoMana && python -m pylint src/automana/services/card_catalog/card_service.py --disable=all --enable=E,F 2>&1 | head -20`

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
cd /home/arthur/projects/AutoMana
git add src/automana/services/card_catalog/card_service.py
git commit -m "refactor: remove unreachable exception branch in card search"
```

---

## Testing

### Task 10: Run Existing Tests to Verify No Regression

**Files:**
- Test: `tests/integration/services/card_catalog/test_card_service.py`
- Test: `tests/integration/services/auth/test_auth_services.py`

- [ ] **Step 1: Run card service tests**

Run: `cd /home/arthur/projects/AutoMana && python -m pytest tests/integration/services/card_catalog/test_card_service.py -v`

Expected: All tests pass. Watch for async-related failures (e.g., "coroutine was never awaited").

- [ ] **Step 2: Run auth service tests**

Run: `cd /home/arthur/projects/AutoMana && python -m pytest tests/integration/services/auth/test_auth_services.py -v`

Expected: All tests pass.

- [ ] **Step 3: Run eBay integration tests**

Run: `cd /home/arthur/projects/AutoMana && python -m pytest tests/integration/services/app_integration/ebay -v`

Expected: All tests pass. Should now skip import of dead cache module.

- [ ] **Step 4: Inspect any failures**

If a test fails with "coroutine was never awaited" or "TypeError: object is not iterable", it likely indicates a missing `await` in the cache calls. Review the error and update the relevant service file.

Run: `cd /home/arthur/projects/AutoMana && python -m pytest tests/integration/services/card_catalog/test_card_service.py::test_name -xvs`

(Replace `test_name` with the failing test.)

- [ ] **Step 5: Commit passing tests as checkpoint**

```bash
cd /home/arthur/projects/AutoMana
git add -A
git commit -m "test: verify async cache migration — all tests passing"
```

---

## Summary

This plan fixes 9 of the 12 issues identified in the cache review:

**Critical:**
1. ✅ Async Redis migration (Task 2-5)
2. ✅ Price history caching (Task 6)
3. ✅ Error handling in cache utility (Task 2)

**High:**
4. ✅ Config in settings (Task 1)
5. ✅ Triple encode/decode (Task 3)
6. ✅ Print statements (Task 8)

**Medium:**
7. ✅ Dead eBay cache module (Task 7)
8. ✅ Unreachable branches (Task 9)
9. ✅ Serialization standardization (Task 2 — uses orjson everywhere)

**Not Addressed (Low Priority):**
- Cache invalidation on manual insert endpoints (architectural decision: acceptable for ETL-only inserts)
- Docs update (Task-based, can be separate)

---
