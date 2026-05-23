"""eBay sold-price persistence — nightly promotion to price_observation.

Reads both staging tables (own-sales and external-scrape), aggregates by
(source_product_id, date, finish_id, condition_id, language_id), upserts
into pricing.price_observation, then marks staging rows as promoted.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
from automana.core.framework.registry import ServiceRegistry

logger = logging.getLogger(__name__)

_EBAY_DATA_PROVIDER_ID = 4
_SELL_PRICE_TYPE_ID = 1
_BATCH_SIZE = 1000


def _aggregate(rows: list[dict], fx_map: dict[str, float] | None = None) -> dict[tuple, dict]:
    """Group rows into (source_product_id, ts_date, finish_id, condition_id, language_id) buckets.

    fx_map maps currency codes → USD rate (e.g. {"AUD": 0.645, "CAD": 0.731}).
    Rows with currency absent or 'USD' are not converted.
    Rows with an unknown currency are passed through at face value.
    """
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
        raw_cents = row.get("sold_price_cents") or row.get("price_cents") or 0
        currency = (row.get("currency") or "USD").upper()
        if fx_map and currency != "USD" and currency in fx_map:
            price_cents = round(raw_cents * fx_map[currency])
        else:
            price_cents = raw_cents
        bucket = groups[key]
        bucket["total"] += price_cents
        bucket["count"] += 1
        id_key = "ebay_osp_id" if "ebay_osp_id" in row else "scrape_id"
        bucket["ids"].append(row[id_key])
    return groups


@ServiceRegistry.register(
    path="integrations.ebay.promote_sold_obs",
    db_repositories=["ebay_sales", "ebay_scrape", "fx_rates"],
    runs_in_transaction=False,
)
async def promote_sold_obs(
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    fx_rates_repository: FxRatesRepository,
) -> dict:
    """Promote unpromoted staging rows from both channels into price_observation."""
    rate_rows = await fx_rates_repository.get_rates_for_date(date.today())
    fx_map: dict[str, float] = {r["from_currency"]: r["rate"] for r in rate_rows}
    if not fx_map:
        logger.warning("promote_sold_obs_no_fx_rates", extra={"date": str(date.today())})

    own_promoted = await _promote_channel(
        staging_rows=await ebay_sales_repository.get_unpromoted(),
        mark_fn=lambda ids: ebay_sales_repository.mark_promoted(ids),
        upsert_fn=ebay_sales_repository.upsert_price_observation,
        fx_map=None,  # own-sales are always USD
    )
    scrape_promoted = await _promote_channel(
        staging_rows=await ebay_scrape_repository.get_unpromoted(),
        mark_fn=lambda ids: ebay_scrape_repository.mark_promoted(ids),
        upsert_fn=ebay_sales_repository.upsert_price_observation,
        fx_map=fx_map or None,
    )
    total = own_promoted + scrape_promoted
    logger.info(
        "ebay_promote_sold_obs_complete",
        extra={"own_promoted": own_promoted, "scrape_promoted": scrape_promoted},
    )
    return {"promoted": total}


async def _promote_channel(staging_rows, mark_fn, upsert_fn, fx_map: dict[str, float] | None = None) -> int:
    if not staging_rows:
        return 0

    groups = _aggregate(staging_rows, fx_map=fx_map)
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
