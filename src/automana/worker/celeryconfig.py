import os
from celery.schedules import crontab
from dotenv import load_dotenv
from automana.core.config.settings import env_file_path
from urllib.parse import urlsplit, urlunsplit

# Load the same env file strategy used by the backend app.
_env_file = env_file_path()
if _env_file:
    load_dotenv(_env_file, override=False)


def _running_in_container() -> bool:
    return os.path.exists("/.dockerenv") or bool(os.getenv("KUBERNETES_SERVICE_HOST"))


def _fix_redis_host(url: str) -> str:
    """Replace the 'redis' service-name hostname with 'localhost' when not in a container.

    .env.dev hard-codes ``redis://redis:6379/…`` for Docker use.  When Celery
    runs on the host (TUI, manual invocation) that hostname is unresolvable, so
    swap it out here rather than requiring a separate env file.
    """
    if _running_in_container():
        return url
    parts = urlsplit(url)
    if parts.hostname == "redis":
        fixed_netloc = parts.netloc.replace("redis:", "localhost:", 1)
        return urlunsplit(parts._replace(netloc=fixed_netloc))
    return url


_default_redis_host = "redis" if _running_in_container() else "localhost"

broker_url = _fix_redis_host(os.getenv("BROKER_URL", f"redis://{_default_redis_host}:6379/0"))
result_backend = _fix_redis_host(os.getenv("RESULT_BACKEND", f"redis://{_default_redis_host}:6379/1"))


imports = {
    "automana.worker.tasks.pipelines",
    "automana.worker.tasks.analytics",
    "automana.worker.tasks.pricing",
    "automana.worker.tasks.ebay",
    "automana.worker.tasks.ebay_actions",
}


worker_prefetch_multiplier = 1
task_always_eager = False
task_store_eager_result = True

# Redis broker redelivery window. Tasks run with acks_late=True, so a message
# is only acked once its task returns. Redis re-queues any message left
# un-acked longer than `visibility_timeout`, which then re-executes on the
# next pickup (or any worker restart). The default is 1h — far shorter than
# our long pipeline steps (e.g. the ~11h mtgstock slice download), so the
# default guarantees duplicate downloads. 24h sits comfortably above the
# longest single task message. The `run_service` redelivery guard
# (ops.pipeline_services.is_run_finished) is the belt to this suspenders:
# it no-ops a redelivered step whose ingestion run already finished.
broker_transport_options = {"visibility_timeout": 86400}

timezone = os.getenv("CELERY_TIMEZONE", "Australia/Sydney")

beat_schedule = {
    "refresh-scryfall-manifest-nightly": {
        "task": "automana.worker.tasks.pipelines.daily_scryfall_data_pipeline",
        "schedule": crontab(hour=2, minute=0),  # 02:00 AEST
    },
    "refresh-mtgjson-daily": {
        "task": "automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline",
        "schedule": crontab(hour=3, minute=0),  # 03:00 AEST
    },
    "daily-analytics-report": {
        "task": "automana.worker.tasks.analytics.daily_summary_analytics_task",
        "schedule": crontab(hour=5, minute=0),  # 05:00 AEST — after all data pipelines
    },
    "pipeline-health-am": {
        "task": "automana.worker.tasks.pipelines.pipeline_health_alert_task",
        "schedule": crontab(hour=6, minute=0),  # 06:00 AEST — post-pipeline check
    },
    "pipeline-health-pm": {
        "task": "automana.worker.tasks.pipelines.pipeline_health_alert_task",
        "schedule": crontab(hour=18, minute=0)  # 18:00 AEST — same-day insuranc
    },
    "log-analysis-daily": {
        "task": "automana.worker.tasks.pipelines.log_analysis_daily_task",
        "schedule": crontab(hour=7, minute=30),  # 07:30 AEST — after all nightly pipelines
    },
    # Card-catalog data-shape health (identifier coverage, orphan unique_cards,
    # external-id collisions) — runs once a day after the daily ingests.
    # `timezone` above resolves to Australia/Sydney, so crontab values are AEST.
    "card-catalog-health-daily": {
        "task": "run_service",
        "schedule": crontab(hour=4, minute=15),  # 04:15 AEST
        "kwargs": {"path": "ops.integrity.card_catalog_report"},
    },
    # Pricing data-quality health (freshness, per-source coverage, soft-integrity,
    # staging drain) — runs hourly because freshness can degrade in <24h.
    # `:42` keeps it off the on-the-hour Celery cluster.
    "pricing-health-hourly": {
        "task": "run_service",
        "schedule": crontab(minute=42),
        "kwargs": {"path": "ops.integrity.pricing_report"},
    },
    # Pricing tier aggregation: refresh daily aggregates from raw observations.
    # Links source_product_id → card_version_id via mtg_card_products table.
    # Runs at 05:30 AEST after MTGStock import completes (04:00).
    "pricing-refresh-daily-aggregates": {
        "task": "refresh_daily_prices",
        "schedule": crontab(hour=5, minute=30),  # 05:30 AEST
    },
    # Pricing tier archival: move Tier 2 (daily) to Tier 3 (weekly) for data >5y.
    # Reduces storage usage and speeds up daily price queries.
    "pricing-archive-to-weekly": {
        "task": "archive_to_weekly_prices",
        "schedule": crontab(day_of_week=0, hour=5, minute=45),  # Sunday 05:45 AEST
    },
    "shopify-ingest-weekly": {
        "task": "automana.worker.tasks.pipelines.shopify_weekly_pipeline",
        "schedule": crontab(day_of_week=0, hour=6, minute=0),  # Sunday 06:00 AEST
    },
    # eBay sold-price persistence — own sales (Fulfillment API, 90-day window).
    "ebay-sync-own-sales-nightly": {
        "task": "automana.worker.tasks.ebay.ebay_sync_own_sales_task",
        "schedule": crontab(hour=7, minute=0),   # 07:00 AEST
    },
    # eBay sold-price promotion — promote own-sales (Fulfillment) plus any
    # externally-written scrape rows (e.g. TCGPLAYER) into price_observation.
    # Runs after own-sales sync (07:00).
    "ebay-promote-sold-obs-nightly": {
        "task": "run_service",
        "schedule": crontab(hour=10, minute=30),  # 10:30 AEST
        "kwargs": {"path": "integrations.ebay.promote_sold_obs"},
    },
    # FX rates: fetch AUD→USD and CAD→USD from frankfurter.app. Kept for future
    # cross-currency price normalisation; the pricing.fx_rates table is retained.
    "pricing-fetch-fx-rates-nightly": {
        "task": "run_service",
        "schedule": crontab(hour=6, minute=45),   # 06:45 AEST
        "kwargs": {"path": "integrations.pricing.fetch_fx_rates"},
    },
    # Weekly cleanup of eBay raw JSON files older than 7 days.
    "ebay-cleanup-raw-files-weekly": {
        "task": "automana.worker.tasks.ebay.ebay_cleanup_raw_files_task",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),  # Sunday 03:00 AEST
    },
    # Drain staging pricing actions → apply to eBay listings every 5 minutes.
    "drain-listing-actions": {
        "task": "automana.worker.tasks.ebay_actions.drain_listing_actions_task",
        "schedule": crontab(minute="*/5"),
    },
    # Open TCG API pricing (tcgtracking.com): SKU-level TCGPlayer market+low prices.
    # API refreshes at 08:00 EST (23:00 AEST). Run at 01:00 AEST — after the
    # daily cache refresh but before the Scryfall pipeline at 02:00 AEST.
    "open-tcg-pricing-daily": {
        "task": "automana.worker.tasks.pipelines.open_tcg_pricing_pipeline",
        "schedule": crontab(hour=1, minute=0),  # 01:00 AEST
    },
    # Weekly mtgstock_id -> card_version_id mapping build.
    # Runs at 02:00 AEST Sunday, after discover-new-ids (01:00) so new IDs are mapped same run.
    "mtgstock-build-id-mapping": {
        "task": "automana.worker.tasks.pipelines.mtgstock_build_id_mapping",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 02:00 AEST
    },
    # MTGStock tiered multi-market refresh.
    # Tier 1 (recent/valuable, 4 markets): 4 daily slots over a 7-day window.
    "mtgstock-tier1-slot0": {
        "task": "automana.worker.tasks.pipelines.mtgstock_tier1_refresh",
        "schedule": crontab(hour=0, minute=30),   # 00:30 AEST
        "kwargs": {"slot": 0},
    },
    "mtgstock-tier1-slot1": {
        "task": "automana.worker.tasks.pipelines.mtgstock_tier1_refresh",
        "schedule": crontab(hour=6, minute=30),   # 06:30 AEST
        "kwargs": {"slot": 1},
    },
    "mtgstock-tier1-slot2": {
        "task": "automana.worker.tasks.pipelines.mtgstock_tier1_refresh",
        "schedule": crontab(hour=12, minute=0),   # 12:00 AEST
        "kwargs": {"slot": 2},
    },
    "mtgstock-tier1-slot3": {
        "task": "automana.worker.tasks.pipelines.mtgstock_tier1_refresh",
        "schedule": crontab(hour=17, minute=0),   # 17:00 AEST
        "kwargs": {"slot": 3},
    },
    # Tier 2 ($1-$5, tcg+cardmarket): 1 daily slot over a 14-day window.
    "mtgstock-tier2": {
        "task": "automana.worker.tasks.pipelines.mtgstock_tier2_refresh",
        "schedule": crontab(hour=8, minute=30),   # 08:30 AEST
    },
    # Tier 3 (bulk, tcg only): 1 daily slot over a 30-day window.
    "mtgstock-tier3": {
        "task": "automana.worker.tasks.pipelines.mtgstock_tier3_refresh",
        "schedule": crontab(hour=14, minute=30),  # 14:30 AEST
    },
    # Incremental DB load: stage all of today's refreshed IDs into price_observation.
    # Runs at 23:00 AEST after all 6 slice downloads have had time to complete.
    "mtgstock-incremental-load": {
        "task": "automana.worker.tasks.pipelines.mtgstock_incremental_load",
        "schedule": crontab(hour=22, minute=0),   # 22:00 AEST
    },
    # Weekly new-ID discovery: probe API for print IDs above current local maximum.
    "mtgstock-discover-new-ids": {
        "task": "automana.worker.tasks.pipelines.mtgstock_discover_new_ids",
        "schedule": crontab(hour=1, minute=0, day_of_week=0),  # Sunday 01:00 AEST
    },
}


