import asyncio
import json
import logging
from pathlib import Path

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.app_integration.mtg_stock.identifier_repository import (
    MtgstockIdentifierRepository,
)
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.services.ops.pipeline_services import track_step

logger = logging.getLogger(__name__)

_SEM = asyncio.Semaphore(50)


@ServiceRegistry.register(
    "mtg_stock.identifier.build_mapping",
    db_repositories=["mtg_stock_identifier", "ops"],
)
async def build_mtgstock_id_mapping(
    mtg_stock_identifier_repository: MtgstockIdentifierRepository,
    destination_folder: str,
    ingestion_run_id: int,
    batch_size: int = 500,
    ops_repository: OpsRepository | None = None,
) -> dict:
    """Resolve print_id → card_version_id from info.json files and upsert into card_external_identifier."""
    ids_path = Path(destination_folder) / "existing_ids.json"
    all_ids: list[int] = json.loads(ids_path.read_text())

    existing = await mtg_stock_identifier_repository.get_existing_mapped_print_ids()
    unmapped = [i for i in all_ids if i not in existing]

    logger.info(
        "MTGStock ID mapping starting",
        extra={"total": len(all_ids), "already_mapped": len(existing), "to_process": len(unmapped)},
    )

    mapped = 0
    unresolved = 0

    async def _read_info(print_id: int) -> dict | None:
        info_path = Path(destination_folder) / str(print_id) / "info.json"
        if not info_path.exists():
            return None
        async with _SEM:
            return await asyncio.to_thread(
                lambda: json.loads(info_path.read_text())
            )

    async with track_step(ops_repository, ingestion_run_id, "build_mtgstock_id_mapping"):
        for batch_start in range(0, len(unmapped), batch_size):
            batch_ids = unmapped[batch_start: batch_start + batch_size]
            info_results = await asyncio.gather(*[_read_info(pid) for pid in batch_ids])

            id_data = [
                {
                    "print_id": pid,
                    "scryfall_id": info.get("scryfallId"),
                    "tcg_id": str(info["tcg_id"]) if info.get("tcg_id") else None,
                    "set_abbr": (info.get("card_set") or {}).get("abbreviation"),
                    "collector_number": str(info.get("collector_number", "")),
                }
                for pid, info in zip(batch_ids, info_results)
                if info is not None
            ]

            # Count IDs with no info.json on disk
            missing_info = sum(1 for info in info_results if info is None)
            unresolved += missing_info

            resolved: dict[int, str] = {}

            # Step 1: scryfall_id
            scryfall_lookup = {d["scryfall_id"]: d["print_id"] for d in id_data if d.get("scryfall_id")}
            if scryfall_lookup:
                matches = await mtg_stock_identifier_repository.fetch_by_scryfall(
                    list(scryfall_lookup)
                )
                for sid, cv_id in matches.items():
                    resolved[scryfall_lookup[sid]] = cv_id

            # Step 2: tcgplayer_id
            remaining = [d for d in id_data if d["print_id"] not in resolved and d.get("tcg_id")]
            if remaining:
                tcg_lookup = {d["tcg_id"]: d["print_id"] for d in remaining}
                matches = await mtg_stock_identifier_repository.fetch_by_tcgplayer(list(tcg_lookup))
                for tid, cv_id in matches.items():
                    resolved[tcg_lookup[tid]] = cv_id

            # Step 3: set_abbr + collector_number
            remaining = [
                d for d in id_data
                if d["print_id"] not in resolved and d.get("set_abbr") and d.get("collector_number")
            ]
            if remaining:
                pair_to_pid = {(d["set_abbr"], d["collector_number"]): d["print_id"] for d in remaining}
                matches = await mtg_stock_identifier_repository.fetch_by_set_collector(
                    list(pair_to_pid)
                )
                for pair, cv_id in matches.items():
                    pid = pair_to_pid.get(pair)
                    if pid and pid not in resolved:
                        resolved[pid] = cv_id

            # IDs that had info.json but still could not be resolved
            still_unresolved = len(id_data) - len(resolved)
            unresolved += still_unresolved

            if resolved:
                mappings = [
                    {"card_version_id": cv_id, "print_id": pid}
                    for pid, cv_id in resolved.items()
                ]
                inserted = await mtg_stock_identifier_repository.upsert_mtgstock_id_mappings(mappings)
                mapped += inserted

            logger.info(
                "MTGStock ID mapping batch complete",
                extra={
                    "batch_start": batch_start,
                    "resolved": len(resolved),
                    "unresolved": missing_info + still_unresolved,
                },
            )

    return {"mapped": mapped, "skipped_existing": len(existing), "unresolved": unresolved}
