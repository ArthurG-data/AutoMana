"""Unit tests for _idempotency — InMemoryIdempotencyStore, RedisIdempotencyStore, singleton."""
import pytest
from unittest.mock import MagicMock

pytestmark = [pytest.mark.unit, pytest.mark.service]


class TestInMemoryIdempotencyStore:
    def _make(self):
        from automana.core.services.app_integration.ebay._idempotency import InMemoryIdempotencyStore
        return InMemoryIdempotencyStore()

    def test_get_miss_returns_none(self):
        store = self._make()
        assert store.get("nonexistent") is None

    def test_set_then_get_returns_value(self):
        store = self._make()
        store.set_if_absent("k", "v")
        assert store.get("k") == "v"

    def test_set_if_absent_returns_true_on_first_write(self):
        store = self._make()
        assert store.set_if_absent("k", "v1") is True

    def test_set_if_absent_returns_false_on_duplicate(self):
        store = self._make()
        store.set_if_absent("k", "v1")
        assert store.set_if_absent("k", "v2") is False

    def test_second_set_does_not_overwrite(self):
        """Idempotency contract: first writer wins."""
        store = self._make()
        store.set_if_absent("k", "first")
        store.set_if_absent("k", "second")
        assert store.get("k") == "first"

    def test_independent_keys_do_not_interfere(self):
        store = self._make()
        store.set_if_absent("a", "alpha")
        store.set_if_absent("b", "beta")
        assert store.get("a") == "alpha"
        assert store.get("b") == "beta"


class TestRedisIdempotencyStore:
    def _make(self, client=None):
        from automana.core.services.app_integration.ebay._idempotency import RedisIdempotencyStore
        return RedisIdempotencyStore(client or MagicMock())

    def test_get_constructs_namespaced_key(self):
        client = MagicMock()
        client.get.return_value = None
        store = self._make(client)

        store.get("my-key")

        client.get.assert_called_once_with("ebay:idempotency:my-key")

    def test_get_returns_decoded_bytes(self):
        client = MagicMock()
        client.get.return_value = b"cached-result"
        store = self._make(client)

        assert store.get("k") == "cached-result"

    def test_get_returns_none_on_cache_miss(self):
        client = MagicMock()
        client.get.return_value = None
        store = self._make(client)

        assert store.get("k") is None

    def test_get_returns_none_on_redis_error(self):
        """Redis errors are swallowed and treated as cache miss."""
        client = MagicMock()
        client.get.side_effect = Exception("connection refused")
        store = self._make(client)

        assert store.get("k") is None

    def test_set_if_absent_passes_nx_and_ttl(self):
        client = MagicMock()
        client.set.return_value = True
        store = self._make(client)

        store.set_if_absent("k", "v", ttl_seconds=3600)

        client.set.assert_called_once_with("ebay:idempotency:k", "v", nx=True, ex=3600)

    def test_set_if_absent_returns_true_when_stored(self):
        client = MagicMock()
        client.set.return_value = True
        store = self._make(client)

        assert store.set_if_absent("k", "v") is True

    def test_set_if_absent_returns_false_when_key_exists(self):
        client = MagicMock()
        client.set.return_value = None  # redis SETNX returns None when key exists
        store = self._make(client)

        assert store.set_if_absent("k", "v") is False

    def test_set_if_absent_returns_false_on_redis_error(self):
        """Redis errors are swallowed; caller proceeds without dedup."""
        client = MagicMock()
        client.set.side_effect = Exception("timeout")
        store = self._make(client)

        assert store.set_if_absent("k", "v") is False


class TestGetIdempotencyStoreSingleton:
    def setup_method(self):
        from automana.core.services.app_integration.ebay._idempotency import set_idempotency_store
        set_idempotency_store(None)

    def teardown_method(self):
        from automana.core.services.app_integration.ebay._idempotency import set_idempotency_store
        set_idempotency_store(None)

    def test_returns_same_instance_on_repeated_calls(self):
        from automana.core.services.app_integration.ebay._idempotency import (
            get_idempotency_store,
            InMemoryIdempotencyStore,
            set_idempotency_store,
        )
        store = InMemoryIdempotencyStore()
        set_idempotency_store(store)

        assert get_idempotency_store() is store
        assert get_idempotency_store() is store

    def test_set_idempotency_store_overrides_default(self):
        from automana.core.services.app_integration.ebay._idempotency import (
            get_idempotency_store,
            InMemoryIdempotencyStore,
            set_idempotency_store,
        )
        custom = InMemoryIdempotencyStore()
        set_idempotency_store(custom)

        assert get_idempotency_store() is custom

    def test_clearing_store_triggers_reinitialisation(self):
        """After set_idempotency_store(None), get_idempotency_store builds a new one."""
        from automana.core.services.app_integration.ebay._idempotency import (
            get_idempotency_store,
            InMemoryIdempotencyStore,
            set_idempotency_store,
        )
        first = InMemoryIdempotencyStore()
        set_idempotency_store(first)
        set_idempotency_store(None)

        # Will rebuild (Redis unavailable in test → falls back to InMemory)
        rebuilt = get_idempotency_store()
        assert rebuilt is not first
