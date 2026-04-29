"""MTGJson download & staging service functions.

Every function here is a thin Service-layer orchestrator: it wires together an
API or DB repository with the StorageService and returns a plain dict of
context keys for the next pipeline step to consume. No business logic lives in
this file that couldn't be named in one sentence — that's by design.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from automana.core.service_registry import ServiceRegistry
from automana.core.repositories.app_integration.mtgjson.Apimtgjson_repository import ApimtgjsonRepository
from automana.core.repositories.app_integration.mtgjson.mtgjson_repository import MtgjsonRepository
from automana.core.storage import StorageService

# Module-level logger — per CLAUDE.md logging rules. Re-fetching `getLogger`
# inside every function (as the previous version did) is pointless: `getLogger`
# is idempotent, but calling it on every invocation is both noisy and a tell
# that someone copy-pasted the pattern without thinking.
logger = logging.getLogger(__name__)


# Size of each COPY batch. 10k rows × ~100 B per row ≈ 1 MB per batch —
# big enough to amortise the COPY round-trip, small enough to keep memory
# flat and to give asyncpg a chance to interleave with other work.
_COPY_BATCH_SIZE = 10_000


@ServiceRegistry.register(
    "mtgjson.data.download.last90",
    api_repositories=["mtgjson"],
    storage_services=["mtgjson"],
)
async def download_mtgjson_data_last_90(
    mtgjson_repository: ApimtgjsonRepository,
    storage_service: StorageService,
) -> dict:
    """Stream the 90-day `AllPrices.json.xz` archive directly to disk.

    Not wired into the active daily chain — kept as a registered entry point
    for manual catch-ups or future weekly pipelines.
    """
    logger.info("Starting MTGJson 90-day price download")
    dest_path = storage_service.build_timestamped_path("AllPrices.json.xz")
    await mtgjson_repository.fetch_all_prices_stream(dest_path)
    logger.info("Streamed MTGJson 90-day data to disk", extra={"file": str(dest_path)})
    return {"file_path_prices": str(dest_path)}


@ServiceRegistry.register(
    "mtgjson.data.download.today",
    api_repositories=["mtgjson"],
    storage_services=["mtgjson"],
)
async def stage_mtgjson_data(
    mtgjson_repository: ApimtgjsonRepository,
    storage_service: StorageService,
) -> dict:
    """Stream today's `AllPricesToday.json.xz` directly to disk.

    Returns `file_path_prices` so the next chain step
    (`staging.mtgjson.stream_to_staging`) can decompress and stage it.
    """
    logger.info("Starting MTGJson today prices download")
    dest_path = storage_service.build_timestamped_path("AllPricesToday.json.xz")
    await mtgjson_repository.fetch_price_today_stream(dest_path)
    logger.info("Streamed MTGJson today prices to disk", extra={"file": str(dest_path)})
    return {"file_path_prices": str(dest_path)}


@ServiceRegistry.register(
    "staging.mtgjson.sync_uuid_mappings",
    db_repositories=["mtgjson"],
    storage_services=["mtgjson"],
)
async def sync_uuid_mappings(
    mtgjson_repository: MtgjsonRepository,
    storage_service: StorageService,
    identifiers_filename: str = "AllIdentifiers.json",
) -> dict:
    """Populate card_external_identifier.mtgjson_id from AllIdentifiers.json.

    AllIdentifiers.json (downloaded from MTGJson) maps each card UUID to its
    scryfallId and other external identifiers. This service extracts
    (mtgjson_uuid, scryfallId) pairs and upserts them via the existing
    scryfall_id rows in card_external_identifier, giving the promoter proc
    the UUID→card_version_id mapping it needs to resolve staged price rows.

    Prerequisites: Scryfall catalog must be loaded first (scryfall_id rows
    must exist). Operation is idempotent — safe to re-run after catalog updates.

    Default filename resolves to {DATA_DIR}/mtgjson/raw/AllIdentifiers.json.
    Pass --identifiers_filename to override.
    """
    logger.info("Loading MTGJson identifier mappings", extra={"file": identifiers_filename})
    raw = await storage_service.load_json(identifiers_filename)

    data = raw.get("data", raw)
    pairs: list[tuple[str, str]] = []
    for mtgjson_uuid, card_data in data.items():
        scryfall_id = card_data.get("identifiers", {}).get("scryfallId")
        if scryfall_id:
            pairs.append((mtgjson_uuid, scryfall_id))

    logger.info(
        "MTGJson UUID pairs extracted",
        extra={"total_uuids": len(data), "with_scryfall_id": len(pairs)},
    )
    inserted = await mtgjson_repository.upsert_mtgjson_id_mappings(pairs)
    logger.info(
        "mtgjson_id mappings upserted",
        extra={"inserted": inserted, "skipped": len(pairs) - inserted},
    )
    return {"mappings_inserted": inserted}


def _iter_card_rows(card_uuid: str, card: Any) -> list[tuple]:
    """Fan out one MTGJson card entry into rows for the staging table.

    MTGJson nests prices as
        card.paper.<source>.<price_type>.<finish>.<date> = <price_float>
    with ``<source>`` also carrying a sibling ``"currency"`` scalar we lift
    onto every row derived from that source. Anything that doesn't match the
    shape is skipped rather than raising — upstream shape drift shouldn't
    bring down the whole pipeline.
    """
    rows: list[tuple] = []
    if not isinstance(card, dict):
        return rows
    paper = card.get("paper")
    if not isinstance(paper, dict):
        return rows

    for source_name, source_val in paper.items():
        if not isinstance(source_val, dict):
            continue
        currency = source_val.get("currency") or "USD"
        for price_type, finishes in source_val.items():
            if price_type == "currency" or not isinstance(finishes, dict):
                continue
            for finish, dates in finishes.items():
                if not isinstance(dates, dict):
                    continue
                for date_str, price_value in dates.items():
                    try:
                        price_date = date.fromisoformat(date_str)
                        price_float = float(price_value)
                    except (TypeError, ValueError):
                        # Bad cell: log and skip so the rest of the card loads.
                        continue
                    rows.append((
                        card_uuid,
                        source_name,
                        price_type,
                        finish,
                        currency,
                        price_float,
                        price_date,
                    ))
    return rows


@ServiceRegistry.register(
    "staging.mtgjson.stream_to_staging",
    db_repositories=["mtgjson"],
    storage_services=["mtgjson"],
)
async def stream_to_staging(
    mtgjson_repository: MtgjsonRepository,
    storage_service: StorageService,
    file_path_prices: str,
) -> dict:
    """Stream an MTGJson `.xz` payload into `pricing.mtgjson_card_prices_staging`.

    Pipeline-contract note: `file_path_prices` is the key produced by both
    ``mtgjson.data.download.today`` and ``mtgjson.data.download.last90`` — the
    ``run_service`` dispatcher filters by signature, so the name is load-bearing.

    Memory stays flat regardless of payload size because decompression + JSON
    parsing happens in a background thread and flows through a bounded queue
    (see ``StorageService.iter_xz_json_kvitems``). Rows are COPY-ed into
    Postgres in batches of ``_COPY_BATCH_SIZE``.
    """
    logger.info("Streaming MTGJson payload to staging", extra={"file": file_path_prices})

    # Serialize concurrent streamers against this staging table. See
    # docs/MTGJSON_PIPELINE.md §"Concurrency" for the rationale — cheap
    # insurance against cron + manual-trigger collisions.
    await mtgjson_repository.acquire_streaming_lock()

    batch: list[tuple] = []
    total_rows = 0
    cards_seen = 0

    async for card_uuid, card in storage_service.iter_xz_json_kvitems(
        file_path_prices, prefix="data"
    ):
        cards_seen += 1
        batch.extend(_iter_card_rows(card_uuid, card))
        if len(batch) >= _COPY_BATCH_SIZE:
            total_rows += await mtgjson_repository.copy_staging_batch(batch)
            batch = []

    if batch:
        total_rows += await mtgjson_repository.copy_staging_batch(batch)

    logger.info(
        "MTGJson streaming complete",
        extra={"cards": cards_seen, "rows_staged": total_rows, "file": file_path_prices},
    )
    return {"rows_staged": total_rows, "cards_seen": cards_seen}


@ServiceRegistry.register(
    "staging.mtgjson.promote_to_price_observation",
    db_repositories=["mtgjson"],
    # The underlying proc issues COMMIT/ROLLBACK per batch, which Postgres
    # forbids when CALL is invoked from an atomic block. Running without
    # an outer transaction lets the proc's own checkpointing do its job.
    runs_in_transaction=False,
    # A fresh 90-day staging load runs for several minutes (normalisation
    # passes + per-batch upserts across millions of rows). 1h is a loose
    # safety net — far above observed durations, well below "hung forever".
    command_timeout=3600,
)
async def promote_to_price_observation(
    mtgjson_repository: MtgjsonRepository,
) -> dict:
    """Promote staged rows into `pricing.price_observation` via the batched proc."""
    logger.info("Promoting MTGJson staged data to price observations")
    await mtgjson_repository.promote_staging_to_production()
    logger.info("Promotion complete")
    return {}


# Default daily-snapshot retention. 29 = "keep roughly a month of daily .xz
# files on disk, always with today's still present". A fresh bulk archive
# (AllPrices_*.json.xz) trumps this and purges all dailies — the bulk
# subsumes them, so retaining both would just burn disk.
_DEFAULT_DAILY_RETENTION = 29


@ServiceRegistry.register(
    "staging.mtgjson.cleanup_raw_files",
    storage_services=["mtgjson"],
)
async def cleanup_raw_files(
    storage_service: StorageService,
    retention_days: int = _DEFAULT_DAILY_RETENTION,
) -> dict:
    """Trim the on-disk MTGJson `.xz` archive to a sliding retention window.

    Two composable rules:
    - Sliding window: keep the newest ``retention_days`` ``AllPricesToday_*``
      files (lexicographic sort on the timestamped filename), delete the rest.
    - Bulk override: if any ``AllPrices_*.json.xz`` bulk archive is present,
      delete **all** daily snapshots — the bulk file subsumes them.

    Per-file delete failures are logged and skipped; one bad path shouldn't
    block the sweep.
    """
    all_files = await storage_service.list_directory(pattern="*.json.xz")

    dailies = sorted(f for f in all_files if f.startswith("AllPricesToday_"))
    bulks = [
        f for f in all_files
        if f.startswith("AllPrices_") and not f.startswith("AllPricesToday_")
    ]

    if bulks:
        to_delete = list(dailies)
    elif len(dailies) > retention_days:
        to_delete = dailies[:-retention_days]
    else:
        to_delete = []

    deleted = 0
    for filename in to_delete:
        try:
            if await storage_service.delete_file(filename):
                deleted += 1
        except Exception as exc:
            logger.warning(
                "Failed to delete MTGJson raw file",
                extra={"file": filename, "error": str(exc)},
            )

    logger.info(
        "MTGJson raw cleanup complete",
        extra={
            "deleted": deleted,
            "retained_dailies": max(0, len(dailies) - deleted),
            "bulk_present": bool(bulks),
        },
    )
    return {"files_deleted": deleted}
