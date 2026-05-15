import ijson
import json
import logging
from datetime import date, timezone

from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops.pipeline_services import track_step
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)

PRICE_KEY_MAP = {
    "usd":        ("tcg",         "NONFOIL"),
    "usd_foil":   ("tcg",         "FOIL"),
    "usd_etched": ("tcg",         "ETCHED"),
    "eur":        ("cardmarket",   "NONFOIL"),
    "eur_foil":   ("cardmarket",   "FOIL"),
    "tix":        ("cardhoarder",  "NONFOIL"),
}

BATCH_SIZE = 500


@ServiceRegistry.register(
    "staging.scryfall.load_prices_from_bulk",
    db_repositories=["pricing", "card", "ops"],
    storage_services=["scryfall"],
)
async def load_scryfall_prices(
    pricing_repository,   # PricingTierRepository (injected by name "pricing")
    card_repository,      # CardReferenceRepository (injected by name "card")
    ops_repository,       # OpsRepository (injected by name "ops")
    storage_service: StorageService = None,  # scryfall StorageService
    file_name: str = None,
    ingestion_run_id: int = None,
) -> dict:
    """Load Scryfall live prices and purchase URIs from a bulk JSON file."""

    if not file_name:
        logger.info(
            "No bulk file available — skipping price load",
            extra={"ingestion_run_id": ingestion_run_id},
        )
        return {"prices_loaded": 0}

    total_count = 0
    ts_date = date.today()

    async with track_step(ops_repository, ingestion_run_id, "load_prices_from_bulk"):
        price_batch: list[dict] = []
        uri_batch: list[dict] = []

        async with storage_service.open_stream(file_name, "rb") as f:
            for card in ijson.items(f, "item"):
                scryfall_id = card.get("id")
                if not scryfall_id:
                    continue

                prices = card.get("prices") or {}
                for key, (source_code, finish_code) in PRICE_KEY_MAP.items():
                    raw = prices.get(key)
                    if raw is None:
                        continue
                    try:
                        price_cents = round(float(raw) * 100)
                    except (ValueError, TypeError):
                        continue
                    price_batch.append(
                        {
                            "scryfall_id": scryfall_id,
                            "source_code": source_code,
                            "finish_code": finish_code,
                            "price_cents": price_cents,
                        }
                    )

                purchase_uris = card.get("purchase_uris")
                if purchase_uris:
                    uri_batch.append(
                        {
                            "scryfall_id": scryfall_id,
                            "purchase_uris": purchase_uris,
                        }
                    )

                # Flush batches when either hits BATCH_SIZE
                if len(price_batch) >= BATCH_SIZE:
                    n = await pricing_repository.upsert_scryfall_price_batch(
                        price_batch, ts_date=ts_date
                    )
                    total_count += n
                    logger.info(
                        "Price batch upserted",
                        extra={"batch_size": len(price_batch), "upserted": n, "ingestion_run_id": ingestion_run_id},
                    )
                    price_batch = []

                if len(uri_batch) >= BATCH_SIZE:
                    await card_repository.update_purchase_uris_batch(uri_batch)
                    uri_batch = []

        # Flush remaining rows
        if price_batch:
            n = await pricing_repository.upsert_scryfall_price_batch(
                price_batch, ts_date=ts_date
            )
            total_count += n
            logger.info(
                "Price batch upserted (final)",
                extra={"batch_size": len(price_batch), "upserted": n, "ingestion_run_id": ingestion_run_id},
            )

        if uri_batch:
            await card_repository.update_purchase_uris_batch(uri_batch)

    logger.info(
        "Scryfall price load complete",
        extra={"prices_loaded": total_count, "ingestion_run_id": ingestion_run_id},
    )
    return {"prices_loaded": total_count}
