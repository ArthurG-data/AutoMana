import logging
from datetime import date

from automana.core.framework.registry import ServiceRegistry
from automana.core.services.ops.pipeline_services import track_step

logger = logging.getLogger(__name__)

# Open TCG API var → card_finished.code
_FINISH_MAP: dict[str, str] = {
    "N": "NONFOIL",
    "F": "FOIL",
    "E": "ETCHED",
}

# Open TCG API cnd → card_condition.code
_CONDITION_MAP: dict[str, str] = {
    "NM": "NM",
    "LP": "LP",
    "MP": "MP",
    "HP": "HP",
    "D":  "DMG",
}

# Open TCG API lng → language_ref.language_code
_LANGUAGE_MAP: dict[str, str] = {
    "EN": "en",
    "FR": "fr",
    "DE": "de",
    "ES": "es",
    "IT": "it",
    "PT": "pt",
    "JP": "jp",
    "KO": "ko",
    "RU": "ru",
    "ZHS": "zh",
    "ZHT": "zh",
}

_BATCH_SIZE = 2000


def _to_cents(val) -> int | None:
    if val is None:
        return None
    try:
        return round(float(val) * 100)
    except (TypeError, ValueError):
        return None


@ServiceRegistry.register(
    "pricing.opentcg.load_prices",
    db_repositories=["pricing", "ops"],
    api_repositories=["open_tcg"],
)
async def load_opentcg_prices(
    pricing_repository,
    ops_repository,
    open_tcg_repository,
    ingestion_run_id: int = None,
) -> dict:
    """Fetch SKU-level TCGPlayer prices from the Open TCG API and upsert into price_observation."""

    total_count = 0
    ts_date = date.today()

    async with track_step(ops_repository, ingestion_run_id, "load_opentcg_prices"):
        async with open_tcg_repository:
            sets = await open_tcg_repository.get_sets()

        set_ids = [s["id"] for s in sets if "id" in s]
        logger.info("opentcg_sets_fetched", extra={"set_count": len(set_ids)})

        batch: list[dict] = []

        async with open_tcg_repository:
            all_skus = await open_tcg_repository.get_all_set_skus(set_ids)

        for set_id, skus in all_skus.items():
            for sku in skus:
                product_id = sku.get("product_id")
                var = sku.get("var", "N")
                cnd = sku.get("cnd", "NM")
                lng = sku.get("lng", "EN")

                finish_code = _FINISH_MAP.get(var)
                condition_code = _CONDITION_MAP.get(cnd)
                language_code = _LANGUAGE_MAP.get(lng)

                if not finish_code or not condition_code or not language_code:
                    continue

                mkt_cents = _to_cents(sku.get("mkt"))
                low_cents = _to_cents(sku.get("low"))

                if mkt_cents is None and low_cents is None:
                    continue

                batch.append(
                    {
                        "tcgplayer_id": product_id,
                        "source_code": "tcg",
                        "finish_code": finish_code,
                        "condition_code": condition_code,
                        "language_code": language_code,
                        "list_avg_cents": mkt_cents or 0,
                        "list_low_cents": low_cents or 0,
                        "list_count": sku.get("cnt", 0) or 0,
                    }
                )

                if len(batch) >= _BATCH_SIZE:
                    n = await pricing_repository.upsert_opentcg_price_batch(batch, ts_date=ts_date)
                    total_count += n
                    logger.info(
                        "opentcg_price_batch_upserted",
                        extra={"batch_size": len(batch), "upserted": n},
                    )
                    batch = []

        if batch:
            n = await pricing_repository.upsert_opentcg_price_batch(batch, ts_date=ts_date)
            total_count += n
            logger.info(
                "opentcg_price_batch_upserted_final",
                extra={"batch_size": len(batch), "upserted": n},
            )

    logger.info("opentcg_price_load_complete", extra={"prices_loaded": total_count})
    return {"prices_loaded": total_count}
