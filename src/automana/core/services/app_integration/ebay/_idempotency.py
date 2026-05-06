"""Idempotency store for eBay listing creation.

Design patterns
───────────────
- **Strategy** via `typing.Protocol`: `IdempotencyStore` declares the contract
  (``get`` / ``set_if_absent``); swap implementations without touching the
  services. If Redis goes away, replace the class, not the call sites.
- **Null Object / Graceful Degradation**: a cache outage must NOT fail a
  create. `RedisIdempotencyStore.*` swallows connection errors with a
  warning log and returns as if the cache were simply empty. The worst case
  degrades to "no dedup for this one call" — not "user sees a 500".
- **Lazy Singleton** via `get_idempotency_store()`: the registry doesn't
  support cache injection, so a module-level accessor is the least-ugly
  option. Tests can override via `set_idempotency_store(...)`.
- **Template Method (lite)**: both implementations share the same two-op
  interface; only the backend differs.

Why Redis `SETNX` + TTL rather than a database table? Because a Redis
round-trip is ~1ms, a Postgres write is 10x that, and idempotency keys are
pure plumbing — they don't need durability past the TTL horizon (24 h here).
We are not committing this to the historical record; we are preventing a
double-click.

Reserved `LogRecord` names — `filename`, `module`, `lineno`, `message` — MUST
NOT appear in ``extra={}``. Use `idempotency_key`, `cache_backend`, etc.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# 24 h in seconds. Long enough for any reasonable client retry window,
# short enough that a compromised key space self-heals in a day.
DEFAULT_IDEMPOTENCY_TTL_SECONDS: int = 24 * 60 * 60


@runtime_checkable
class IdempotencyStore(Protocol):
    """Minimal contract. Two operations, no inheritance required."""

    def get(self, key: str) -> Optional[str]:
        """Return the cached value for `key`, or None if absent / unavailable."""
        ...

    def set_if_absent(
        self, key: str, value: str, ttl_seconds: int = DEFAULT_IDEMPOTENCY_TTL_SECONDS
    ) -> bool:
        """Atomic SETNX. Returns True if stored, False if key already existed."""
        ...


class InMemoryIdempotencyStore:
    """Process-local store. Great for tests, useless for a multi-worker prod.

    Uses a lock because asyncio + threaded Celery workers share memory and we
    refuse to ship a data race. TTL is NOT enforced here — this class exists
    to make tests deterministic, not to simulate Redis eviction. If you need
    TTL simulation, use fakeredis.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            return self._data.get(key)

    def set_if_absent(
        self, key: str, value: str, ttl_seconds: int = DEFAULT_IDEMPOTENCY_TTL_SECONDS
    ) -> bool:
        with self._lock:
            if key in self._data:
                return False
            self._data[key] = value
            return True


class RedisIdempotencyStore:
    """Redis-backed store using `SET key value NX EX ttl`.

    A cache outage is logged and treated as cache-miss / store-noop — the
    caller proceeds, a duplicate create is theoretically possible, and we
    accept that over returning 500 when Redis is wobbling.
    """

    KEY_PREFIX = "ebay:idempotency:"

    def __init__(self, client) -> None:  # noqa: ANN001 — duck-typed redis client
        # Accept anything with `.get(...)` and `.set(..., nx=..., ex=...)`.
        # That's every redis-py client we care about (sync or async, wrapped
        # or raw). We intentionally keep this synchronous to match the
        # existing `automana.core.utils.redis_cache` wiring. If you move to
        # async redis, swap this class — don't awkwardly async-ify a module
        # that nothing else awaits.
        self._client = client

    def _namespaced(self, key: str) -> str:
        return f"{self.KEY_PREFIX}{key}"

    def get(self, key: str) -> Optional[str]:
        try:
            raw = self._client.get(self._namespaced(key))
        except Exception as exc:
            logger.warning(
                "idempotency_cache_get_failed",
                extra={
                    "action": "idempotency_get",
                    "idempotency_key": key,
                    "error": str(exc),
                    "cache_backend": "redis",
                },
            )
            return None
        if raw is None:
            return None
        # redis-py returns bytes by default unless decode_responses=True.
        return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)

    def set_if_absent(
        self, key: str, value: str, ttl_seconds: int = DEFAULT_IDEMPOTENCY_TTL_SECONDS
    ) -> bool:
        try:
            result = self._client.set(
                self._namespaced(key), value, nx=True, ex=ttl_seconds
            )
        except Exception as exc:
            logger.warning(
                "idempotency_cache_set_failed",
                extra={
                    "action": "idempotency_set",
                    "idempotency_key": key,
                    "error": str(exc),
                    "cache_backend": "redis",
                },
            )
            return False
        return bool(result)


# ────────────────────────── module-level singleton ──────────────────────────
# The registry has no cache-injection knob today; a lazy singleton is the
# pragmatic choice. Tests should call `set_idempotency_store(...)`. Production
# wiring happens at app startup (see TODO below).

_store: Optional[IdempotencyStore] = None
_store_lock = threading.Lock()


def set_idempotency_store(store: Optional[IdempotencyStore]) -> None:
    """Inject a store (tests) or clear it (None → revert to default)."""
    global _store
    with _store_lock:
        _store = store


def get_idempotency_store() -> IdempotencyStore:
    """Return the active store, building a default lazily on first access.

    Default strategy: try the project's existing sync Redis client; if import
    or connection setup fails, fall back to an in-memory store with a loud
    warning so ops can see that dedup is running on a single process. We do
    NOT crash startup over a cache problem.

    TODO(startup-wiring): pick up a ready-configured Redis client from
    `core/settings.py` once `REDIS_URL` lands, instead of importing the
    legacy `automana.core.utils.redis_cache.redis_client` module-level.
    """
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is not None:
            return _store
        try:
            # Late import: keep redis out of the import path for tests that
            # don't touch idempotency. Uses a dedicated sync Redis client
            # because RedisIdempotencyStore explicitly requires sync .get()/.set().
            import redis as _redis_lib
            from automana.core.settings import get_settings as _get_settings

            _settings = _get_settings()
            _sync_client = _redis_lib.Redis.from_url(
                _settings.redis_cache_url, decode_responses=False
            )
            _store = RedisIdempotencyStore(_sync_client)
            logger.debug(
                "idempotency_store_initialised",
                extra={"cache_backend": "redis"},
            )
        except Exception as exc:
            logger.warning(
                "idempotency_store_fallback_in_memory",
                extra={
                    "error": str(exc),
                    "cache_backend": "memory",
                },
            )
            _store = InMemoryIdempotencyStore()
        return _store
