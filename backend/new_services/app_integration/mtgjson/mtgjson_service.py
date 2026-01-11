from backend.core.service_registry import ServiceRegistry
import logging, json
import asyncio

async def download_mtgjson_data(repository, storage_service):
    logger = logging.getLogger(__name__)
    logger.info("Starting MTGJSON data download")

    try:
        card_data = await repository.fetch_card_data([])
        logger.info("Fetched MTGJSON card data successfully")

        await storage_service.store_data("mtgjson_card_data.json", card_data)
        logger.info("Stored MTGJSON card data successfully")
    except Exception as e:
        logger.error("Error during MTGJSON data download: %s", e)
        raise

@ServiceRegistry.register(
        "mtgjson.data.staging.all",
        db_repositories=["Mtgjson"],
)
async def stage_mtgjson_data(mtgjson_repository, path):
    logger = logging.getLogger(__name__)
    logger.info("Starting MTGJSON data staging")

    try:
        data = json.load(open(path, "r"))
        await mtgjson_repository.stage_card_data(data)
        logger.info("Staged MTGJSON card data successfully")
    except Exception as e:
        logger.error("Error during MTGJSON data staging: %s", e)
        raise