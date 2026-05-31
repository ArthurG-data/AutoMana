"""Broker transport options regression guards.

The Redis broker defaults to a 1h ``visibility_timeout``. With ``acks_late=True``
any task whose single message outlives that window gets redelivered and
re-executed (observed: an ~11h mtgstock slice re-downloading after a restart).
``visibility_timeout`` must exceed the longest single task message.
"""
from automana.worker import celeryconfig


def test_broker_visibility_timeout_exceeds_longest_task():
    opts = getattr(celeryconfig, "broker_transport_options", {})
    # 24h: comfortably above the ~11h worst-case slice download step.
    assert opts.get("visibility_timeout", 0) >= 86400
