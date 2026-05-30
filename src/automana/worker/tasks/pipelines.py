from celery import group, shared_task, chain
import json
import logging
from pathlib import Path
from automana.worker.main import run_service
from automana.core.log.logging_context import set_task_id
from datetime import datetime, date
from automana.core.services.ops.log_analysis_service import run_daily_log_summary  # noqa: F401 — registers service
from automana.core.services.app_integration.mtg_stock import identifier_service  # noqa: F401 — registers service

logger = logging.getLogger(__name__)

@shared_task(name="automana.worker.tasks.pipelines.daily_scryfall_data_pipeline", bind=True)
def daily_scryfall_data_pipeline(self):
    set_task_id(self.request.id)
    run_key = f"scryfall_daily:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting Scryfall daily pipeline", extra={"run_key": run_key})
    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return
    wf = chain(
        run_service.s("staging.scryfall.start_pipeline",#new test
                      pipeline_name="scryfall_daily",
                      source_name="scryfall",
                      run_key=run_key,
                      celery_task_id=self.request.id
                      ),
        run_service.s("staging.scryfall.get_bulk_data_uri"),#get the uri for the bulk data manifest
        run_service.s("staging.scryfall.download_bulk_manifests"),#download the bulk data manifest
        run_service.s("staging.scryfall.update_data_uri_in_ops_repository"),#from the manifest, update the db and get the list of uris to download
        run_service.s("staging.scryfall.download_sets"),
        run_service.s("card_catalog.set.process_large_sets_json"), 
        run_service.s("staging.scryfall.download_cards_bulk"),
        run_service.s("card_catalog.card.process_large_json"),
        run_service.s("staging.scryfall.load_prices_from_bulk"),
        run_service.s("card_catalog.card_search.refresh"),
        run_service.s("card_catalog.card_search.invalidate"),
        # Migrations must land AFTER the card import: `new_scryfall_id` values
        # reference rows we just upserted into `card_catalog.card_version`,
        # and any pipeline that resolves deprecated IDs via
        # `COALESCE(m.new_scryfall_id, original_id)` (e.g. MTGStock) expects
        # the migration table to be current. Idempotency on re-runs is
        # enforced at the repository layer (staging table + ON CONFLICT DO
        # NOTHING) — not with `autoretry_for`, per project rule: retries are
        # the concern of `run_service`, not the pipeline task.
        run_service.s("staging.scryfall.download_and_load_migrations"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
        run_service.s("staging.scryfall.delete_old_scryfall_folders", keep=3),
        # Diagnostic integrity checks — run AFTER finish_run so that a failing
        # check does NOT mark the pipeline run as failed.  These are read-only
        # sanity checks; their output is informational, not blocking.
        run_service.s("ops.integrity.scryfall_run_diff"),
        run_service.s("ops.integrity.scryfall_integrity"),
        run_service.s("ops.integrity.public_schema_leak"),
    )
    return wf.apply_async().id
 
@shared_task(name="automana.worker.tasks.pipelines.mtgStock_download_pipeline", bind=True)
def mtgStock_download_pipeline(self):
    set_task_id(self.request.id)
    run_key = f"mtgStock_All:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting MTGStock download pipeline", extra={"run_key": run_key})
    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return
    # Chain shape: start → bulk_load → raw→stg → retry_rejects → stg→observation → finish.
    # `retry_rejects` calls pricing.resolve_price_rejects() to re-feed any
    # previously-rejected rows that can now be resolved (e.g. via new scryfall
    # migration entries or freshly-seeded external identifiers), so they make
    # it into today's price_observation promotion rather than lingering in
    # `stg_price_observation_reject`.
    # `source_name` is the `pricing.price_source.code` value used both by
    # `ops.start_run` (for provenance) and by `from_raw_to_staging` (when
    # calling the staging procedure).
    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtg_stock_all",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id
                      ),
        run_service.s("mtg_stock.data_staging.bulk_load",
                      root_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=2000,
                      market="tcg"
                      ),
        run_service.s("mtg_stock.data_staging.from_raw_to_staging",
                      source_name="mtgstocks"),
        run_service.s("mtg_stock.data_staging.retry_rejects"),
        run_service.s("mtg_stock.data_staging.from_staging_to_prices"),
        run_service.s("ops.pipeline_services.finish_run", status="success" )
    )
    return wf.apply_async().id


@shared_task(name="automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline", bind=True)
def daily_mtgjson_data_pipeline(self):
    # NB: `datetime.utcnow()` is deprecated in 3.12+ and scheduled for removal.
    # Prefer `datetime.now(timezone.utc)` — keeping utcnow() here only because
    # the sibling pipelines above still use it; a consistent project-wide swap
    # belongs in its own PR.
    set_task_id(self.request.id)
    run_key = f"mtgjson_daily:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting MTGJson daily pipeline", extra={"run_key": run_key})
    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    # Why `check_version` is NOT wired in here:
    # `check_version` compares the MTGJson `Meta.json` catalog version, which
    # tracks *set/printing* releases — it changes at most a few times a week.
    # This pipeline downloads `AllPricesToday.json.xz`, which changes *daily*
    # regardless of catalog version. Gating a daily price feed on a catalog
    # version is a category error: you'd miss every price update between
    # catalog publications. `check_version` is the right gate for the 90-day
    # / AllPrintings flow (a future `mtgjson_weekly` pipeline), not this one.
    #
    # Secondary reason: `run_service` has no "skip the rest of the chain"
    # semantics. Returning `version_changed=False` from a gate step does not
    # stop the downstream `download.today` call — each step always runs. A
    # proper gate would need either (a) a Celery `group`/signature that short
    # -circuits, or (b) downstream steps that inspect `version_changed` and
    # no-op themselves. Neither is in place today.
    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgjson_daily",
                      source_name="mtgjson",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        # Download fresh AllIdentifiers.json so UUID→scryfallId mappings are
        # current before prices are staged. Returns identifiers_filename for
        # sync_uuid_mappings to consume via run_service context-merge.
        run_service.s("mtgjson.data.download.all_identifiers"),
        # Idempotent: ON CONFLICT DO NOTHING skips duplicates on re-runs.
        # Must run before download.today so the promoter can resolve every
        # card_uuid staged in this run.
        run_service.s("staging.mtgjson.sync_uuid_mappings"),
        run_service.s("mtgjson.data.download.today"),
        # Consumes `file_path_prices` from the download step. Streams the
        # compressed payload directly into `pricing.mtgjson_card_prices_staging`
        # via lzma + ijson + asyncpg COPY — no intermediate JSONB archive.
        # See migration 15 for the rationale (JSONB blobs of 1–2 GB were
        # tripping the 60 s command_timeout on insert).
        run_service.s("staging.mtgjson.stream_to_staging"),
        # Promotes staged rows into `pricing.price_observation` and deletes
        # resolved rows from staging. No parameters — operates over the
        # whole staging table.
        run_service.s("staging.mtgjson.promote_to_price_observation"),
        # Truncate any staging rows that promotion couldn't resolve (DFC gap
        # cards not yet in the catalog). Logged as a warning, not an error.
        run_service.s("staging.mtgjson.cleanup_staging_db"),
        # Aggregate T1 price_observation → T2 print_price_daily for today.
        # No date args: the proc reads tier_watermark.last_processed_date to
        # pick up exactly where the previous run left off (up to yesterday).
        run_service.s("pricing.refresh_daily_prices"),
        run_service.s("card_catalog.card_search.refresh"),
        run_service.s("card_catalog.card_search.invalidate"),
        # Sliding-window retention on the on-disk .xz archive. Runs inside
        # the tracked run so cleanup failures surface as a failed step
        # (rather than silently accumulating stale files).
        run_service.s("staging.mtgjson.cleanup_raw_files"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id


@shared_task(name="automana.worker.tasks.pipelines.daily_mtgjson_sealed_pipeline", bind=True)
def daily_mtgjson_sealed_pipeline(self):
    """Promote any staged sealed prices and refresh the sealed_price_latest snapshot.

    Expects sealed UUIDs to already exist in pricing.sealed_products
    (bootstrap_catalog must be called at least once when new sets are released).
    The promotion procedure handles its own batching and commits.
    """
    set_task_id(self.request.id)
    run_key = f"mtgjson_sealed:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting MTGJson sealed pricing pipeline", extra={"run_key": run_key})
    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgjson_sealed",
                      source_name="mtgjson",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("pricing.sealed.promote_staging"),
        run_service.s("pricing.sealed.cleanup_staging"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id


@shared_task(name="automana.worker.tasks.pipelines.open_tcg_pricing_pipeline", bind=True)
def open_tcg_pricing_pipeline(self):
    set_task_id(self.request.id)
    run_key = f"opentcg_pricing:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting Open TCG pricing pipeline", extra={"run_key": run_key})
    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return
    wf = chain(
        run_service.s(
            "ops.pipeline_services.start_run",
            pipeline_name="opentcg_pricing",
            source_name="tcgtracking",
            run_key=run_key,
            celery_task_id=self.request.id,
        ),
        run_service.s("pricing.opentcg.load_prices"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id


@shared_task(name="run_scryfall_integrity_checks", bind=True)
def run_scryfall_integrity_checks(self):
    """Dispatch all three Scryfall integrity-check services in parallel.

    The three services are independent read-only diagnostics; using ``group``
    rather than ``chain`` lets them run concurrently across available workers.
    The results are collected by the group's result set — no aggregation is
    performed in this task itself; callers that need a combined report should
    inspect the group result via Celery's result backend.

    This task can be scheduled independently (e.g. nightly after the
    scryfall_daily pipeline) or triggered ad-hoc from the TUI / HTTP endpoint.
    """
    set_task_id(self.request.id)
    logger.info(
        "Launching Scryfall integrity checks",
        extra={"celery_task_id": self.request.id},
    )
    wf = group(
        run_service.s("ops.integrity.scryfall_run_diff"),
        run_service.s("ops.integrity.scryfall_integrity"),
        run_service.s("ops.integrity.public_schema_leak"),
    )
    return wf.apply_async().id


@shared_task(bind=True, name="automana.worker.tasks.pipelines.pipeline_health_alert_task")
def pipeline_health_alert_task(self):
    """Twice-daily Celery Beat job: run all ops.integrity.* services, persist
    a snapshot, and post a transition-only Discord alert.

    Per project rules this task does NOT use ``autoretry_for``; retry policy
    lives at the run_service layer. A failure here is logged via Celery's
    standard machinery and does not retry — twice-daily cadence makes the
    next scheduled invocation the recovery path.
    """
    return run_service("ops.health.alert_check")


@shared_task(bind=True, name="automana.worker.tasks.pipelines.log_analysis_daily_task")
def log_analysis_daily_task(self) -> dict:
    """Daily Celery Beat job: query Loki for last 24h of ERROR logs, summarise
    with Claude, and post a digest to Discord.

    Per project rules this task does NOT use ``autoretry_for``; retry policy
    lives at the run_service layer.
    """
    return run_service("ops.log_analysis.daily_summary")


@shared_task(name="automana.worker.tasks.pipelines.shopify_weekly_pipeline", bind=True)
def shopify_weekly_pipeline(self):
    """Weekly Celery Beat job: fetch /products.json from every registered Shopify
    storefront, process to parquet, stage into pricing.shopify_staging_raw, and
    promote into pricing.price_observation.

    Per project rules this task does NOT use ``autoretry_for``; retry policy
    lives at the run_service layer.
    """
    set_task_id(self.request.id)
    run_key = f"shopify_weekly:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting Shopify weekly pipeline", extra={"run_key": run_key})
    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return
    wf = chain(
        run_service.s(
            "ops.pipeline_services.start_run",
            pipeline_name="shopify_weekly",
            source_name="shopify",
            run_key=run_key,
            celery_task_id=self.request.id,
        ),
        run_service.s("shopify.pipeline.fetch_all_markets"),
        run_service.s("shopify.pipeline.process_to_parquet"),
        run_service.s("shopify.pipeline.stage_raw"),
        run_service.s("shopify.pipeline.promote_observations"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id


@shared_task(name="automana.worker.tasks.pipelines.mtgstock_build_id_mapping", bind=True)
def mtgstock_build_id_mapping(self):
    """Weekly: resolve print_id → card_version_id and populate card_external_identifier."""
    set_task_id(self.request.id)
    today = datetime.utcnow().date().isoformat()
    run_key = f"mtgStock_id_mapping:{today}"
    logger.info("Starting MTGStock ID mapping build", extra={"run_key": run_key})
# ── MTGStock rolling refresh ──────────────────────────────────────────────────

_MTGSTOCK_IDS_PATH = Path("/data/automana_data/mtgstocks/raw/prints/existing_ids.json")
_MTGSTOCK_EPOCH = date(2026, 6, 1)
_WINDOW_DAYS = 7
_RUNS_PER_DAY = 6
_TOTAL_SLICES = _WINDOW_DAYS * _RUNS_PER_DAY  # 42


def _mtgstock_slice_ids(hour_slot: int) -> list[int]:
    """Return the sorted print IDs assigned to this hour_slot on today's date.

    Slice index = (day_offset * 6 + hour_slot) % 42.  Deterministic and
    stateless — identical inputs always produce the same list.
    """
    existing_ids = sorted(json.loads(_MTGSTOCK_IDS_PATH.read_text()))
    total = len(existing_ids)
    slice_size = total // _TOTAL_SLICES

    day_offset = (date.today() - _MTGSTOCK_EPOCH).days
    slice_idx = (day_offset * _RUNS_PER_DAY + hour_slot) % _TOTAL_SLICES

    start = slice_idx * slice_size
    end = start + slice_size if slice_idx < _TOTAL_SLICES - 1 else total
    return existing_ids[start:end]


def _mtgstock_daily_ids() -> list[int]:
    """Return all print IDs assigned to today in the 7-day window.

    Day-in-window = day_offset % 7.  Union of all 6 hour_slot slices for today.
    """
    existing_ids = sorted(json.loads(_MTGSTOCK_IDS_PATH.read_text()))
    total = len(existing_ids)
    daily_size = total // _WINDOW_DAYS

    day_offset = (date.today() - _MTGSTOCK_EPOCH).days
    day_in_window = day_offset % _WINDOW_DAYS
    start = day_in_window * daily_size
    end = start + daily_size if day_in_window < _WINDOW_DAYS - 1 else total
    return existing_ids[start:end]


@shared_task(name="automana.worker.tasks.pipelines.mtgstock_slice_refresh", bind=True)
def mtgstock_slice_refresh(self, hour_slot: int):
    """Fetch one 1/42 slice of MTGStock print IDs from the API and update disk files."""
    set_task_id(self.request.id)
    today = datetime.utcnow().date().isoformat()
    run_key = f"mtgStock_slice:{today}:{hour_slot}"
    logger.info("Starting MTGStock slice refresh", extra={"run_key": run_key, "hour_slot": hour_slot})

    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    slice_ids = _mtgstock_slice_ids(hour_slot)
    logger.info("MTGStock slice computed", extra={"hour_slot": hour_slot, "count": len(slice_ids)})

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgstock_slice_refresh",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("mtg_stock.data_loader.run_list_id_load",
                      destination_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=500,
                      ids_list=slice_ids,
                      market="tcg"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id


@shared_task(name="automana.worker.tasks.pipelines.mtgstock_incremental_load", bind=True)
def mtgstock_incremental_load(self):
    """Stage and promote today's refreshed MTGStock IDs into price_observation."""
    set_task_id(self.request.id)
    today = datetime.utcnow().date().isoformat()
    run_key = f"mtgStock_load:{today}"
    logger.info("Starting MTGStock incremental DB load", extra={"run_key": run_key})

    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    today_ids = _mtgstock_daily_ids()
    logger.info("MTGStock daily IDs computed", extra={"count": len(today_ids)})

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgstock_incremental_load",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("mtg_stock.data_staging.bulk_load",
                      root_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=2000,
                      ids_filter=today_ids,
                      market="tcg"),
        run_service.s("mtg_stock.data_staging.from_raw_to_staging",
                      source_name="mtgstocks"),
        run_service.s("mtg_stock.data_staging.retry_rejects"),
        run_service.s("mtg_stock.data_staging.from_staging_to_prices"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id


@shared_task(name="automana.worker.tasks.pipelines.mtgstock_discover_new_ids", bind=True)
def mtgstock_discover_new_ids(self):
    """Weekly: probe MTGStocks for print IDs beyond the local maximum and download them."""
    set_task_id(self.request.id)
    today = datetime.utcnow().date().isoformat()
    run_key = f"mtgStock_discover:{today}"
    logger.info("Starting MTGStock new ID discovery", extra={"run_key": run_key})

    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgstock_build_id_mapping",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("mtg_stock.identifier.build_mapping",
                      destination_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=500),
                      pipeline_name="mtgstock_discover_new_ids",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("mtg_stock.data_loader.discover_and_fetch_new_ids",
                      destination_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=500,
                      market="tcg"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id
