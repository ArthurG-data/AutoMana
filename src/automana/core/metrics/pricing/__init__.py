"""Importing this package triggers registration of all pricing metrics.

The runner service (`ops.integrity.pricing_report`) imports this module so
that `MetricRegistry.select(prefix="pricing.")` finds every metric without
any caller needing to remember the individual module paths.
"""
from automana.core.metrics.pricing import freshness_metrics      # noqa: F401
from automana.core.metrics.pricing import coverage_metrics       # noqa: F401
from automana.core.metrics.pricing import integrity_metrics      # noqa: F401
from automana.core.metrics.pricing import card_coverage_metrics  # noqa: F401
from automana.core.metrics.pricing import tier_metrics           # noqa: F401
