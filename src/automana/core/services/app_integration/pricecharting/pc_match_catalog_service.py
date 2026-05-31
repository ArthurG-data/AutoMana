"""Step 4 — Match PriceCharting products to card_version_ids (persistent map).

Consumes the JSON emitted by ``pricecharting.scrape_catalog`` (uid-keyed
``sets.json`` + ``products/{uid}.json``) and the TCGPlayer ids/votes from
``pricecharting.scrape_sales`` (``sales/{uid}.json``), and resolves each single
product to a card_version_id with a method + certainty.

The result is persisted in ``pricing.pricecharting_card_map`` so the heuristic
runs ONCE per product: already-resolved (or manually ``verified``) products are
skipped on later runs; unmatched products are always re-attempted so matching
improvements apply. Confident matches also get a ``pricecharting_id`` external
identifier on the card (the durable card_version <-> PC link).
"""
from __future__ import annotations

import logging
from typing import Any

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.app_integration.pricecharting.pc_map_repository import (
    PricechartingMapRepository,
)
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from automana.core.repositories.card_catalog.set_repository import SetReferenceRepository
from automana.core.services.app_integration.pricecharting import pc_matching
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)

# Only confident matches earn the durable card_version <-> pricecharting_id link.
_REGISTER_CERTAINTY_THRESHOLD = 70


async def _load_tcgplayer_ids(storage_service: StorageService, uid: str) -> dict[str, tuple[str, int]]:
    """{pc_product_id: (tcgplayer_id, vote_count)} from a set's sales file, if scraped."""
    sales_key = f"sales/{uid}.json"
    if not await storage_service.file_exists(sales_key):
        return {}
    sales = await storage_service.load_json(sales_key)
    out: dict[str, tuple[str, int]] = {}
    for pid, payload in (sales.get("products") or {}).items():
        tcg_id = payload.get("tcgplayer_id")
        if tcg_id:
            out[pid] = (str(tcg_id), int(payload.get("tcgplayer_id_votes", 0)))
    return out


@ServiceRegistry.register(
    path="pricecharting.build_match_catalog",
    db_repositories=["set", "card", "pricecharting_map"],
    storage_services=["pricecharting"],
)
async def build_match_catalog(
    set_repository: SetReferenceRepository,
    card_repository: CardReferenceRepository,
    pricecharting_map_repository: PricechartingMapRepository,
    storage_service: StorageService,
    **kwargs: Any,
) -> dict:
    """Resolve PriceCharting products to card_versions and persist the matches.

    Requires ``pricecharting.scrape_catalog`` (sets.json + products/{uid}.json).
    """
    if not await storage_service.file_exists("sets.json"):
        logger.warning("pricecharting_match_no_sets_file")
        return {"new_matched": 0, "new_unmatched": 0, "skipped_existing": 0,
                "skipped_sets": 0, "identifiers_registered": 0}

    existing = await pricecharting_map_repository.fetch_all_map()
    db_sets = await set_repository.fetch_sets_for_matching()
    set_index = pc_matching.build_set_code_index([dict(r) for r in db_sets])
    pc_sets = (await storage_service.load_json("sets.json")).get("sets", [])

    upserts: list[dict] = []
    new_matched = new_unmatched = skipped_existing = skipped_sets = identifiers_registered = 0

    for set_info in pc_sets:
        uid = set_info["uid"]
        set_code, set_method = pc_matching.match_set_code(set_info["name"], set_index)
        if not set_code:
            skipped_sets += 1
            continue

        catalog_key = f"products/{uid}.json"
        if not await storage_service.file_exists(catalog_key):
            skipped_sets += 1
            continue

        singles = [
            p for p in (await storage_service.load_json(catalog_key)).get("products", [])
            if p["product_type"] == "single"
        ]
        if not singles:
            continue

        tcg = await _load_tcgplayer_ids(storage_service, uid)

        for product in singles:
            pid = product["product_id"]
            prior = existing.get(pid)
            # Skip the heuristic only for already-resolved or manually-locked rows;
            # always re-attempt recorded misses so matching improvements apply.
            if prior and (prior.get("card_version_id") is not None or prior.get("verified")):
                skipped_existing += 1
                continue

            card_name = pc_matching.clean_card_name(product["title"])
            candidates = await card_repository.fetch_versions_by_set_and_name(set_code, card_name)
            tcg_id, tcg_votes = tcg.get(pid, (None, 0))
            match = pc_matching.resolve_card_match(
                [dict(c) for c in candidates], product["title"], tcg_id,
                set_method=set_method, tcg_votes=tcg_votes,
            )

            if not match:
                upserts.append({"pc_product_id": pid, "card_version_id": None,
                                "set_code": set_code, "finish_id": None,
                                "match_method": "none", "certainty": 0, "tcg_vote_count": tcg_votes})
                new_unmatched += 1
                continue

            upserts.append({
                "pc_product_id": pid,
                "card_version_id": match["card_version_id"],
                "set_code": set_code,
                "finish_id": match["finish_id"],
                "match_method": match["match_method"],
                "certainty": match["certainty"],
                "tcg_vote_count": tcg_votes,
            })
            new_matched += 1

            if match["certainty"] >= _REGISTER_CERTAINTY_THRESHOLD:
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

    submitted = await pricecharting_map_repository.upsert_map(upserts)

    logger.info(
        "pricecharting_match_complete",
        extra={
            "new_matched": new_matched, "new_unmatched": new_unmatched,
            "skipped_existing": skipped_existing, "skipped_sets": skipped_sets,
            "identifiers_registered": identifiers_registered, "rows_upserted": submitted,
        },
    )
    return {
        "new_matched": new_matched,
        "new_unmatched": new_unmatched,
        "skipped_existing": skipped_existing,
        "skipped_sets": skipped_sets,
        "identifiers_registered": identifiers_registered,
    }
