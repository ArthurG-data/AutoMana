"""pricing.tier.* — health and freshness metrics for Tier 2 / Tier 3.

Tier topology recap
───────────────────
  Tier 1  pricing.price_observation        raw hypertable (source-grain)
  Tier 2  pricing.print_price_daily        daily rollup hypertable
  Tier 3  pricing.print_price_weekly       weekly archive hypertable (>5 yr data)
  Track   pricing.tier_watermark           one row per tier; tracks last_processed_date

These metrics answer three operational questions:

1. Are Tier 1 and Tier 2 in sync?
   ``pricing.tier.sync_diff`` — absolute row-count difference.  Should be 0
   on a healthy DB; any positive value triggers a warn.

2. Is Tier 3 archival overdue?
   ``pricing.tier.archival_ready_rows`` — rows in Tier 2 older than 5 years
   that have not yet been promoted by ``archive_to_weekly()``.

3. Are the watermarks fresh?
   ``pricing.tier.daily_watermark_lag_days`` — days behind for the daily tier.
   ``pricing.tier.weekly_watermark_lag_days`` — same for the weekly tier.

All four row-count metrics are wired into the existing metric-registry runner
and will automatically appear in the ``ops.integrity.pricing_report`` and the
new ``ops.integrity.pricing_tier_health`` service outputs because both use the
``pricing.`` prefix.

Note on row-count estimates
───────────────────────────
Tier 2 and Tier 3 are TimescaleDB hypertables.  Their ``reltuples`` ANALYZE
estimates can diverge from the real COUNT(*) by a small percentage between
VACUUM cycles, which is acceptable for monitoring purposes.  If an operator
needs an exact count they should run the psql maintenance script directly.
"""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.app_integration.mtg_stock.price_repository import (
    PriceRepository,
)


@MetricRegistry.register(
    path="pricing.tier.tier2_row_count",
    category="volume",
    description=(
        "Estimated row count of pricing.print_price_daily (Tier 2 daily rollup). "
        "Uses pg_class.reltuples — fast but may lag slightly between ANALYZE runs."
    ),
    # severity=None: zero is expected before refresh_daily_prices() has ever run.
    # Tracking the count as a volume metric is useful; firing alerts on zero would
    # create noise immediately after a full DB rebuild.  Use sync_diff for sync
    # health instead.
    severity=None,
    db_repositories=["price"],
)
async def tier2_row_count(price_repository: PriceRepository) -> MetricResult:
    """Report the Tier 2 (print_price_daily) estimated row count."""
    n = await price_repository.fetch_tier2_row_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.tier.tier3_row_count",
    category="volume",
    description=(
        "Estimated row count of pricing.print_price_weekly (Tier 3 weekly archive). "
        "Zero is expected until archive_to_weekly() has been run for the first time."
    ),
    severity=None,  # Informational — zero is valid until archival begins.
    db_repositories=["price"],
)
async def tier3_row_count(price_repository: PriceRepository) -> MetricResult:
    """Report the Tier 3 (print_price_weekly) estimated row count."""
    n = await price_repository.fetch_tier3_row_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.tier.sync_diff",
    category="health",
    description=(
        "Absolute row-count difference between Tier 1 (price_observation) and "
        "Tier 2 (print_price_daily). Zero means in sync. Any positive value means "
        "refresh_daily_prices() has not processed all Tier 1 rows yet."
    ),
    # Row-count estimates from reltuples are approximate; a diff of up to a few
    # thousand is normal between ANALYZE cycles.  Warn at 100k (noticeable gap),
    # error at 1M (sync is seriously overdue).
    severity=Threshold(warn=100_000, error=1_000_000, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def tier_sync_diff(price_repository: PriceRepository) -> MetricResult:
    """Report the absolute Tier 1 / Tier 2 row-count difference."""
    stats = await price_repository.fetch_tier_sync_diff()
    return MetricResult(
        row_count=stats["diff"],
        details={
            "tier1_rows": stats["tier1_rows"],
            "tier2_rows": stats["tier2_rows"],
        },
    )


@MetricRegistry.register(
    path="pricing.tier.archival_ready_rows",
    category="status",
    description=(
        "Rows in print_price_daily older than 5 years that are eligible to be "
        "promoted to print_price_weekly via archive_to_weekly(). "
        "Non-zero is a soft reminder, not an error — archival is a manual/scheduled op."
    ),
    # Warn when any archivable rows exist; the error threshold is set far above
    # any realistic row count because archival is voluntary — we should never
    # page on this, only surface it as an advisory warning.
    severity=Threshold(warn=1, error=500_000_000, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def archival_ready_rows(price_repository: PriceRepository) -> MetricResult:
    """Report the number of Tier 2 rows eligible for archive_to_weekly()."""
    stats = await price_repository.fetch_archival_ready_row_count(older_than_years=5)
    return MetricResult(
        row_count=stats["archivable_rows"],
        details={"cutoff_date": stats["cutoff_date"]},
    )


@MetricRegistry.register(
    path="pricing.tier.daily_watermark_lag_days",
    category="timing",
    description=(
        "Days since the daily tier watermark was last advanced. "
        "None means refresh_daily_prices() has never run (seed date 1970-01-01). "
        "Warn at 2 days, error at 7 days."
    ),
    severity=Threshold(warn=2, error=7, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def daily_watermark_lag_days(price_repository: PriceRepository) -> MetricResult:
    """Report the daily tier watermark lag in days.

    Returns None when the watermark is at the 1970-01-01 seed (never run),
    which the Threshold evaluator maps to WARN per its None-guard.
    """
    wm = await price_repository.fetch_watermark_lag_days()
    return MetricResult(
        row_count=wm["daily_lag_days"],
        details={"last_processed_date": wm["daily_last_date"]},
    )


@MetricRegistry.register(
    path="pricing.tier.weekly_watermark_lag_days",
    category="timing",
    description=(
        "Days since the weekly tier watermark was last advanced. "
        "None means archive_to_weekly() has never run. "
        "Warn at 14 days, error at 90 days (weekly archival is infrequent)."
    ),
    # The weekly archival is not a daily job — running once every few months
    # for pre-migration data is acceptable.  Wide thresholds avoid alert fatigue.
    severity=Threshold(warn=14, error=90, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def weekly_watermark_lag_days(price_repository: PriceRepository) -> MetricResult:
    """Report the weekly tier watermark lag in days.

    Returns None when the watermark is at the 1970-01-01 seed (never run),
    which the Threshold evaluator maps to WARN per its None-guard.
    """
    wm = await price_repository.fetch_watermark_lag_days()
    return MetricResult(
        row_count=wm["weekly_lag_days"],
        details={"last_processed_date": wm["weekly_last_date"]},
    )
