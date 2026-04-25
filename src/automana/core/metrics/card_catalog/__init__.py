"""Importing this package triggers registration of all card_catalog metrics.

The runner service (`ops.integrity.card_catalog_report`) imports this module
so that `MetricRegistry.select(prefix="card_catalog.")` finds every metric
without any caller needing to remember the individual module paths.
"""
from automana.core.metrics.card_catalog import identifier_metrics  # noqa: F401
from automana.core.metrics.card_catalog import catalog_metrics     # noqa: F401
