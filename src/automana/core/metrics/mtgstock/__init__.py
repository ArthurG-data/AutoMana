"""Importing this package triggers registration of all mtgstock metrics.

The runner service (`ops.integrity.mtgstock_report`) imports this module so
that `MetricRegistry.select(prefix="mtgstock.")` finds every metric without
any caller needing to remember the individual module paths.
"""
from automana.core.metrics.mtgstock import run_metrics  # noqa: F401
from automana.core.metrics.mtgstock import staging_metrics  # noqa: F401
from automana.core.metrics.mtgstock import promotion_metrics  # noqa: F401
