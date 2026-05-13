"""eBay sold-price persistence — nightly promotion to price_observation.

Reads both staging tables (own-sales and external-scrape), aggregates by
(source_product_id, date, finish_id, condition_id, language_id), upserts
into pricing.price_observation, then marks staging rows as promoted.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

_EBAY_DATA_PROVIDER_ID = 4
_SELL_PRICE_TYPE_ID = 1
_BATCH_SIZE = 1000


def _aggregate(rows: list[dict]) -> dict[tuple, dict]:
    """Group rows into (source_product_id, ts_date, finish_id, condition_id, language_id) buckets."""
    groups: dict[tuple, dict] = defaultdict(lambda: {"total": 0, "count": 0, "ids": []})
    for row in rows:
        ts_date = row.get("sold_at")
        if hasattr(ts_date, "date"):
            ts_date = ts_date.date()
        elif not isinstance(ts_date, date):
            continue
        key = (
            row.get("source_product_id"),
            ts_date,
            row.get("finish_id", 1),
            row.get("condition_id") or 1,
            row.get("language_id", 1),
        )
        bucket = groups[key]
        bucket["total"] += row.get("sold_price_cents") or row.get("price_cents") or 0
        bucket["count"] += 1
        id_key = "ebay_osp_id" if "ebay_osp_id" in row else "scrape_id"
        bucket["ids"].append(row[id_key])
    return groups


@ServiceRegistry.register(
    path="integrations.ebay.promote_sold_obs",
    db_repositories=["ebay_sales", "ebay_scrape"],
    runs_in_transaction=False,
)
async def promote_sold_obs(
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    **kwargs: Any,
) -> dict:
    """Promote unpromoted staging rows from both channels into price_observation."""
    own_promoted = await _promote_channel(
        staging_rows=await ebay_sales_repository.get_unpromoted(),
        mark_fn=lambda ids: ebay_sales_repository.mark_promoted(ids),
        upsert_fn=ebay_sales_repository.upsert_price_observation,
    )
    scrape_promoted = await _promote_channel(
        staging_rows=await ebay_scrape_repository.get_unpromoted(),
        mark_fn=lambda ids: ebay_scrape_repository.mark_promoted(ids),
        upsert_fn=ebay_sales_repository.upsert_price_observation,
    )
    total = own_promoted + scrape_promoted
    logger.info(
        "ebay_promote_sold_obs_complete",
        extra={"own_promoted": own_promoted, "scrape_promoted": scrape_promoted},
    )
    return {"promoted": total}


async def _promote_channel(staging_rows, mark_fn, upsert_fn) -> int:
    if not staging_rows:
        return 0

    groups = _aggregate(staging_rows)
    promoted_ids: list[int] = []

    for batch_start in range(0, len(groups), _BATCH_SIZE):
        batch_keys = list(groups.keys())[batch_start:batch_start + _BATCH_SIZE]
        for key in batch_keys:
            source_product_id, ts_date, finish_id, condition_id, language_id = key
            bucket = groups[key]
            avg_cents = round(bucket["total"] / bucket["count"])
            try:
                await upsert_fn(
                    ts_date=ts_date,
                    source_product_id=source_product_id,
                    price_type_id=_SELL_PRICE_TYPE_ID,
                    finish_id=finish_id,
                    condition_id=condition_id,
                    language_id=language_id,
                    data_provider_id=_EBAY_DATA_PROVIDER_ID,
                    sold_avg_cents=avg_cents,
                    sold_count=bucket["count"],
                )
                promoted_ids.extend(bucket["ids"])
            except Exception:
                logger.exception(
                    "ebay_promote_upsert_failed",
                    extra={"source_product_id": source_product_id, "ts_date": str(ts_date)},
                )

    if promoted_ids:
        try:
            await mark_fn(promoted_ids)
        except Exception:
            logger.exception("ebay_promote_mark_failed", extra={"count": len(promoted_ids)})

    return len(promoted_ids)
