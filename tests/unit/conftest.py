"""
Unit-test-only fixtures.
Resets the idempotency singleton before and after every test so that
import-time side effects from listings_write_service do not leak state
between tests regardless of execution order.
"""
import pytest
from automana.core.services.app_integration.ebay._idempotency import (
    InMemoryIdempotencyStore,
    set_idempotency_store,
)


@pytest.fixture(autouse=True)
def reset_idempotency_store():
    """Guarantee singleton isolation for the entire unit suite."""
    store = InMemoryIdempotencyStore()
    set_idempotency_store(store)
    yield store
    set_idempotency_store(None)
