from backend.core.service_registry import ServiceRegistry
from backend.repositories.app_integration.mtgjson.Apimtgjson_repository import ApimtgjsonRepository
from backend.core.storage import StorageService
import logging, json
import asyncio


@ServiceRegistry.register(
        "mtgjson.data.staging.last90",
        api_repositories=["mtgjson"],
        storage_services=["local_storage"]
)
async def download_mtgjson_data_last_90(mtgjson_repository : ApimtgjsonRepository
                                        , storage_service : StorageService
                                        , directory: str = r"G:\data\mtgjson\raw"):
    logger = logging.getLogger(__name__)
    logger.info("Starting MTGJSON data download")

    try:
        #fetch the data from the API repository
        card_data = await mtgjson_repository.fetch_all_prices_data()
        if card_data is None:
            raise ValueError("No data returned from MTGJSON repository")
        logger.info("Fetched MTGJSON card data successfully.")

        await storage_service.save_with_timestamp(directory=directory, filename= "AllPrices.json.xz", data=card_data)
        logger.info("Stored MTGJSON card data successfully")
    except Exception as e:
        logger.error("Error during MTGJSON data download: %s", e)
        raise

@ServiceRegistry.register(
        "mtgjson.data.staging.today",
        api_repositories=["mtgjson"],
        storage_services=["local_storage"]
)
async def stage_mtgjson_data(mtgjson_repository : ApimtgjsonRepository
                             , storage_service: StorageService, 
                             directory: str = r"G:\data\mtgjson\raw"):
    logger = logging.getLogger(__name__)
    logger.info("Starting MTGJSON data staging")

    try:
        #fetch the data from the API repository
        card_data = await mtgjson_repository.fetch_price_today()
        if card_data is None:
            raise ValueError("No data returned from MTGJSON repository")
        logger.info("Fetched MTGJSON card data successfully.")

        await storage_service.save_with_timestamp(directory=directory, filename= "AllPricesToday.json.xz", data=card_data)
        logger.info("Stored MTGJSON card data successfully")
    except Exception as e:
        logger.error("Error during MTGJSON data download: %s", e)
        raise