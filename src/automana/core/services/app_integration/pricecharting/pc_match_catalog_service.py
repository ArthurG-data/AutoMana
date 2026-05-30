"""Step 4 — Match PriceCharting products to card_version_ids and build the catalog.

Consumes the JSON emitted by ``pricecharting.scrape_catalog`` (uid-keyed
``sets.json`` + ``products/{uid}.json``) and, where present, the TCGPlayer ids
from ``pricecharting.scrape_sales`` (``sales/{uid}.json``). For each single
product it:

  1. maps the PC set name -> DB set_code (name-based, see pc_matching),
  2. matches the product to a card_version_id (treatment scoring + tiebreakers),
  3. registers the PC product_id as a ``pricecharting_id`` external identifier
     on the matched card_version (so later runs can resolve by id),

then writes ``catalog.json`` (``{pc_product_id: match | null}``) to storage for
the staging step.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from automana.core.repositories.card_catalog.set_repository import SetReferenceRepository
from automana.core.services.app_integration.pricecharting import pc_matching
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)

_CATALOG_FILE = "catalog.json"


async def _load_tcgplayer_ids(storage_service: StorageService, uid: str) -> dict[str, str]:
    """Return {pc_product_id: tcgplayer_id} from a set's sales file, if scraped."""
    sales_key = f"sales/{uid}.json"
    if not await storage_service.file_exists(sales_key):
        return {}
    sales = await storage_service.load_json(sales_key)
    out: dict[str, str] = {}
    for pid, payload in (sales.get("products") or {}).items():
        tcg_id = payload.get("tcgplayer_id")
        if tcg_id:
            out[pid] = str(tcg_id)
    return out


@ServiceRegistry.register(
    path="pricecharting.build_match_catalog",
    db_repositories=["set", "card"],
    storage_services=["pricecharting"],
)
async def build_match_catalog(
    set_repository: SetReferenceRepository,
    card_repository: CardReferenceRepository,
    storage_service: StorageService,
    force_refresh: bool = False,
    **kwargs: Any,
) -> dict:
    """Build ``catalog.json`` mapping PC product_id -> card_version match.

    Requires ``pricecharting.scrape_catalog`` to have produced ``sets.json`` and
    ``products/{uid}.json``. Cached for the calendar day unless force_refresh.
    """
    if not await storage_service.file_exists("sets.json"):
        logger.warning("pricecharting_match_no_sets_file")
        return {"matched": 0, "unmatched": 0, "skipped_sets": 0, "identifiers_registered": 0}

    if await storage_service.file_exists(_CATALOG_FILE) and not force_refresh:
        existing = await storage_service.load_json(_CATALOG_FILE)
        if existing.get("built_at") == date.today().isoformat():
            logger.info(
                "pricecharting_match_from_cache",
                extra={"matched": existing.get("matched"), "unmatched": existing.get("unmatched")},
            )
            return {
                "matched": existing.get("matched", 0),
                "unmatched": existing.get("unmatched", 0),
                "skipped_sets": existing.get("skipped_sets", 0),
                "identifiers_registered": existing.get("identifiers_registered", 0),
                "from_cache": True,
            }

    # ── Build the set_name -> set_code index once ─────────────────────────────
    db_sets = await set_repository.fetch_sets_for_matching()
    set_index = pc_matching.build_set_code_index([dict(r) for r in db_sets])

    pc_sets = (await storage_service.load_json("sets.json")).get("sets", [])

    catalog: dict[str, dict | None] = {}
    matched = unmatched = skipped_sets = identifiers_registered = 0

    for set_info in pc_sets:
        uid = set_info["uid"]
        set_code, _method = pc_matching.match_set_code(set_info["name"], set_index)
        if not set_code:
            skipped_sets += 1
            continue

        catalog_key = f"products/{uid}.json"
        if not await storage_service.file_exists(catalog_key):
            skipped_sets += 1
            continue

        catalog_data = await storage_service.load_json(catalog_key)
        singles = [p for p in catalog_data.get("products", []) if p["product_type"] == "single"]
        if not singles:
            continue

        tcg_ids = await _load_tcgplayer_ids(storage_service, uid)

        for product in singles:
            pid = product["product_id"]
            card_name = pc_matching.clean_card_name(product["title"])
            candidates = await card_repository.fetch_versions_by_set_and_name(set_code, card_name)
            match = pc_matching.resolve_card_match(
                [dict(c) for c in candidates], product["title"], tcg_ids.get(pid)
            )
            catalog[pid] = match
            if not match:
                unmatched += 1
                continue
            matched += 1

            # Persist the PC product_id as an external identifier on the card.
            try:
                reg = await card_repository.register_external_identifier(
                    match["card_version_id"], "pricecharting_id", pid
                )
                if reg.inserted:
                    identifiers_registered += 1
            except Exception:
                logger.exception(
                    "pricecharting_identifier_register_failed",
                    extra={"product_id": pid, "card_version_id": match["card_version_id"]},
                )

    await storage_service.save_json(_CATALOG_FILE, {
        "built_at": date.today().isoformat(),
        "matched": matched,
        "unmatched": unmatched,
        "skipped_sets": skipped_sets,
        "identifiers_registered": identifiers_registered,
        "catalog": catalog,
    })

    logger.info(
        "pricecharting_match_complete",
        extra={
            "matched": matched,
            "unmatched": unmatched,
            "skipped_sets": skipped_sets,
            "identifiers_registered": identifiers_registered,
        },
    )
    return {
        "matched": matched,
        "unmatched": unmatched,
        "skipped_sets": skipped_sets,
        "identifiers_registered": identifiers_registered,
    }
