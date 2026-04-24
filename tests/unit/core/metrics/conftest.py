"""
Fixtures for the metrics unit tests.

The MetricRegistry is class-level state (a dict). Tests that exercise the
registry's filtering/selection logic need isolation from the real mtgstock
registrations that land at import time. Use ``isolated_registry`` to snapshot
and restore the registry around those tests.

The mtgstock metric function tests and the runner test deliberately do NOT
use this fixture — they require the real registrations to be present.
"""
import pytest
from automana.core.metrics.registry import MetricRegistry


@pytest.fixture
def isolated_registry():
    """Snapshot _metrics, wipe the registry, restore on teardown.

    This is the only safe way to isolate registry state: Python caches modules
    so re-importing mtgstock after clear() is a no-op.
    """
    snapshot = MetricRegistry._metrics.copy()
    MetricRegistry._metrics.clear()
    try:
        yield MetricRegistry
    finally:
        MetricRegistry._metrics = snapshot
