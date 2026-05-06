# Caching Architecture

AutoMana implements a Redis-based application-level caching layer for frequently accessed data. All cache operations are asynchronous and non-blocking.

## Overview

The caching system uses **Redis** as the backing store with:
- **Async I/O** via `redis.asyncio.Redis` (non-blocking, event-loop safe)
- **Error handling** with graceful degradation (cache misses on errors, no 500 responses)
- **Structured logging** for cache operations
- **JSON serialization** via `orjson` for consistency and performance

## Configuration

Cache configuration is managed through `core/settings.py`:

```python
# In core/settings.py
redis_cache_url: str = Field(
    default="redis://localhost:6379/1",
    validation_alias="REDIS_CACHE_URL",
    description="Redis URL for cache operations (separate from Celery broker)"
)
```

**Key points:**
- Uses a separate Redis database (`/1`) from the Celery broker (`/0`)
- All URLs configured via environment variables (never hardcoded)
- Loaded from `REDIS_CACHE_URL` env var (defaults to localhost dev database)

## Cache Utility API

All cache operations go through [`src/automana/core/utils/redis_cache.py`](../src/automana/core/utils/redis_cache.py):

### Reading from Cache

```python
async def get_from_cache(cache_key: str) -> Optional[Any]
```

- Returns `None` on cache miss or error (graceful degradation)
- Automatically deserializes with `orjson.loads()`
- Logs cache read errors to stderr (no exceptions raised)

**Usage:**
```python
cached_result = await get_from_cache(f"card_search:{query_hash}")
if cached_result is not None:
    return cached_result
```

### Writing to Cache

```python
async def set_to_cache(cache_key: str, value: Any, expiry_seconds: int = 3600) -> bool
```

- Returns `True` on success, `False` on error
- Automatically serializes with `orjson.dumps()`
- No-op on Redis failures (logs warning but does not propagate exception)

**Usage:**
```python
result = {"cards": [...], "total_count": 42}
await set_to_cache(f"card_search:{query_hash}", result, expiry_seconds=3600)
```

### Pattern-Based Invalidation

```python
async def invalidate_cache_pattern(pattern: str) -> int
```

- Safely deletes all keys matching a pattern (e.g., `"card_search:*"`)
- Returns the count of deleted keys
- Used during data pipeline runs (e.g., after bulk card imports)

**Usage:**
```python
deleted = await invalidate_cache_pattern("card_search:*")
logger.info("cache_invalidated", extra={"pattern": "card_search:*", "count": deleted})
```

## Current Cache Surfaces

### Card Search (Full)

- **Service:** `card_catalog.card_service.search_cards()`
- **Key:** `card_search:full:{sha256(all_params)}`
- **TTL:** 3600 seconds (1 hour)
- **Invalidation:** Pipeline task `card_catalog.card_search.invalidate` after Scryfall/MTGJson imports

### Card Search (Suggest)

- **Service:** `card_catalog.card_service.suggest_cards()`
- **Key:** `card_search:suggest:{query.lower()}:{limit}`
- **TTL:** 600 seconds (10 minutes)
- **Invalidation:** Same as full search

### Price History

- **Service:** `card_catalog.card_service.get_card_price_history()`
- **Key:** `price_history:{card_id}:{finish}:{days_back}:{aggregation}`
- **TTL:** 86400 seconds (24 hours)
- **Invalidation:** None (price data is immutable once aggregated)

### eBay Tokens (OAuth)

- **Service:** `app_integration.ebay._auth_context` and `auth_services`
- **Key:** `ebay:access_token:{user_id}:{app_code}`
- **TTL:** `expires_in - 60` seconds (before token expiry)
- **Invalidation:** Natural (TTL only)

### eBay Idempotency

- **Service:** `app_integration.ebay._idempotency.IdempotencyStore`
- **Key:** `ebay:idempotency:{key}`
- **TTL:** 86400 seconds (24 hours)
- **Note:** Uses a separate sync Redis client (not the async cache utility)

## Error Handling & Degradation

The cache utility is designed for graceful degradation:

**Read Errors:**
- Cache miss on `RedisError` (connection timeout, server error, etc.)
- Cache miss on deserialization error (corrupted cached data)
- Logged as `warning` (not `error`)
- Service continues with fresh computation

**Write Errors:**
- Silently ignored (returns `False`)
- Logged as `warning`
- No impact on client response
- Data is computed fresh on next request

**Invalidation Errors:**
- Logged as `warning`
- Returns `0` (no keys deleted)
- Does not block pipeline operations

Example flow:
```python
# Read attempt fails -> returns None -> service computes fresh value
cached = await get_from_cache("card_search:xyz")  # Redis down → returns None
if cached is None:
    result = await repository.search(...)  # Compute fresh
    await set_to_cache("card_search:xyz", result)  # Write fails silently if Redis still down
    return result
return cached
```

## Key Naming Conventions

Cache keys follow these patterns:

- **Scoped by function:** `{scope}:{function}:{hash_or_params}`
- **Examples:**
  - `card_search:full:{sha256_hash}` — full search cache
  - `card_search:suggest:{query}:{limit}` — autocomplete cache
  - `price_history:{card_id}:{finish}:{days}:{agg}` — price history
  - `ebay:access_token:{user_id}:{app_code}` — eBay tokens

**Rules:**
- Avoid spaces and special characters
- Use lowercase for consistency
- Include all discriminating parameters (prevent collisions)
- Hash long parameter strings to keep key lengths reasonable

## Adding New Caches

When adding a new cache:

1. **Choose a TTL** based on data freshness requirements:
   - User session data: 30 minutes
   - Search results: 1 hour
   - Price data: 24 hours
   - Real-time data: 5 minutes (or don't cache)

2. **Design the key carefully**:
   - Include all parameters that affect the result
   - Use deterministic hashing if the parameter set is large
   - Test for collision-free keys across expected input ranges

3. **Implement cache read**:
   ```python
   cache_key = f"myfeature:{param1}:{param2}"
   cached = await get_from_cache(cache_key)
   if cached is not None:
       logger.debug("cache_hit", extra={"key": cache_key})
       return reconstruct_result(cached)
   ```

4. **Implement cache write**:
   ```python
   # Compute the result
   result = await expensive_computation()
   
   # Serialize and cache
   cache_data = result.model_dump(mode="json") if hasattr(result, 'model_dump') else result
   await set_to_cache(cache_key, cache_data, expiry_seconds=3600)
   
   return result
   ```

5. **Plan invalidation**:
   - If data changes frequently → lower TTL or don't cache
   - If data changes on predictable events → call `invalidate_cache_pattern()` after those events
   - If data is immutable → no invalidation needed (use long TTL)

## Logging

All cache operations log to stderr with structured fields:

```python
# Cache hit (debug level)
logger.debug("cache_hit", extra={"key": "card_search:xyz"})

# Cache miss due to error (warning level)
logger.warning("cache_read_error", extra={"key": "...", "error": "Connection timeout"})

# Cache write failure (warning level)
logger.warning("cache_write_error", extra={"key": "...", "error": "..."})

# Pattern invalidation
logger.info("cache_invalidated", extra={"pattern": "card_search:*", "count": 42})
```

## Testing

Cache functions are fully async and require `pytest-asyncio`:

```python
@pytest.mark.asyncio
async def test_card_search_caching():
    cache_key = "card_search:full:test123"
    test_data = {"cards": [...], "total_count": 5}
    
    # Write to cache
    success = await set_to_cache(cache_key, test_data, expiry_seconds=60)
    assert success is True
    
    # Read from cache
    cached = await get_from_cache(cache_key)
    assert cached == test_data
    
    # Invalidate
    count = await invalidate_cache_pattern("card_search:*")
    assert count >= 1
```

## Performance Characteristics

- **Cache hits:** ~1-5ms (network round-trip to Redis)
- **Cache misses:** Full computation time + ~1-5ms write attempt
- **Invalidation:** O(n) where n = keys matching pattern (usually <100 for our workloads)

Redis on localhost: ~0.5-1ms per operation.
Redis over network: ~5-50ms depending on latency.

## Known Limitations

- Serialization format: `orjson` (JSON). Non-JSON-serializable types must be converted to dicts or strings before caching.
- Cache keys limited to Redis string key size (~500MB, effectively unlimited for our use case).
- Pattern matching uses `SCAN` internally (no blocking, safe for large keysets).
- No cache statistics built-in (consider Prometheus metrics if cache stats needed).

## Future Improvements

- Add cache statistics to MetricsRegistry (hit/miss/error counts)
- Implement cache warming for predictable access patterns
- Add TTL-aware invalidation (update TTL instead of delete)
- Support compressed serialization for large cached objects
