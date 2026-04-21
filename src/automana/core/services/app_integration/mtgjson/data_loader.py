"""MTGJson download & staging service functions.

Every function here is a thin Service-layer orchestrator: it wires together an
API or DB repository with the StorageService and returns a plain dict of
context keys for the next pipeline step to consume. No business logic lives in
this file that couldn't be named in one sentence — that's by design.
"""
import logging

from automana.core.service_registry import ServiceRegistry
from automana.core.repositories.app_integration.mtgjson.Apimtgjson_repository import ApimtgjsonRepository
from automana.core.repositories.app_integration.mtgjson.mtgjson_repository import MtgjsonRepository
from automana.core.storage import StorageService

# Module-level logger — per CLAUDE.md logging rules. Re-fetching `getLogger`
# inside every function (as the previous version did) is pointless: `getLogger`
# is idempotent, but calling it on every invocation is both noisy and a tell
# that someone copy-pasted the pattern without thinking.
logger = logging.getLogger(__name__)


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
    (`staging.mtgjson.load_prices_to_staging`) can decompress and stage it.
    """
    logger.info("Starting MTGJson today prices download")
    dest_path = storage_service.build_timestamped_path("AllPricesToday.json.xz")
    await mtgjson_repository.fetch_price_today_stream(dest_path)
    logger.info("Streamed MTGJson today prices to disk", extra={"file": str(dest_path)})
    return {"file_path_prices": str(dest_path)}


@ServiceRegistry.register(
    "staging.mtgjson.load_prices_to_staging",
    db_repositories=["mtgjson"],
    storage_services=["mtgjson"],
)
async def load_prices_to_staging(
    mtgjson_repository: MtgjsonRepository,
    storage_service: StorageService,
    file_path_prices: str,
) -> dict:
    """Decompress the on-disk `.xz`, land the payload in `pricing.mtgjson_payloads`,
    then expand it into `pricing.mtgjson_card_prices_staging`.

    The parameter name `file_path_prices` is contractual: it must match the
    return key from any upstream download step (see `stage_mtgjson_data` and
    `download_mtgjson_data_last_90`). `run_service` filters by signature, so
    there is no need — and no value — in accepting `**kwargs` here.
    """
    logger.info("Loading MTGJson prices to staging", extra={"file": file_path_prices})

    # Decompression is CPU-bound; `load_xz_as_json` offloads to a thread.
    payload = await storage_service.load_xz_as_json(file_path_prices)

    payload_id = await mtgjson_repository.insert_payload(
        source="mtgjson",
        filename=file_path_prices,
        payload=payload,
    )
    logger.info("Inserted MTGJson payload", extra={"payload_id": payload_id})

    await mtgjson_repository.call_process_payload(payload_id)
    logger.info("Expanded payload into staging rows", extra={"payload_id": payload_id})

    return {"payload_id": payload_id}


#
@ServiceRegistry.register(
    "staging.mtgjson.promote_to_price_observation",
    db_repositories=["mtgjson"]
)
async def promote_to_price_observation(mtgjson_repository: MtgjsonRepository,
                                        payload_id: int
                                        ) -> dict:
    """Call the stored procedure to promote staged rows into `pricing.mtgjson_card_prices`."""
    logger.info("Promoting MTGJson staged data to price observations", extra={"payload_id": payload_id})
    await mtgjson_repository.promote_staging_to_production(payload_id) 
    logger.info("Promotion complete", extra={"payload_id": payload_id})
    return {"payload_id": payload_id}
