from celery import group, shared_task, chain
import logging
from automana.worker.main import run_service
from automana.core.logging_context import set_task_id
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(name="daily_scryfall_data_pipeline", bind=True)
def daily_scryfall_data_pipeline(self):
    set_task_id(self.request.id)
    run_key = f"scryfall_daily:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting Scryfall daily pipeline", extra={"run_key": run_key})
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
 
@shared_task(name="mtgStock_download_pipeline", bind=True)
def mtgStock_download_pipeline(self):
    set_task_id(self.request.id)
    run_key = f"mtgStock_All:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting MTGStock download pipeline", extra={"run_key": run_key})
    # Chain shape: start → bulk_load → raw→stg → stg→observation → finish.
    # The previously present `from_staging_to_dim` step was removed — the
    # `pricing.load_dim_from_staging` procedure was never created in the DB,
    # and there is no intermediate dim table. The final step calls
    # `pricing.load_prices_from_staged_batched` directly.
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
                      batch_size=1000,
                      market="tcg"
                      ),
        run_service.s("mtg_stock.data_staging.from_raw_to_staging",
                      source_name="mtgstocks"),
        run_service.s("mtg_stock.data_staging.from_staging_to_prices"),
        run_service.s("ops.pipeline_services.finish_run", status="success" )
    )
    return wf.apply_async().id


@shared_task(name="daily_mtgjson_data_pipeline", bind=True)
def daily_mtgjson_data_pipeline(self):
    # NB: `datetime.utcnow()` is deprecated in 3.12+ and scheduled for removal.
    # Prefer `datetime.now(timezone.utc)` — keeping utcnow() here only because
    # the sibling pipelines above still use it; a consistent project-wide swap
    # belongs in its own PR.
    set_task_id(self.request.id)
    run_key = f"mtgjson_daily:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting MTGJson daily pipeline", extra={"run_key": run_key})

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
        # Sliding-window retention on the on-disk .xz archive. Runs inside
        # the tracked run so cleanup failures surface as a failed step
        # (rather than silently accumulating stale files).
        run_service.s("staging.mtgjson.cleanup_raw_files"),
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