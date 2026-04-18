import logging
from automana.core.service_registry import ServiceRegistry
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)

async def insert_mtg_json_data(mtgjson_repository, storage_service):
    """Calles the reuired stored procedure to move the data from file storage to the staging table in the database"""
    logger.info("Starting MTGJSON data staging")

    try:
        #fetch the data from storage

        card_data = await mtgjson_repository.fetch_price_today()
        if card_data is None:
            raise ValueError("No data returned from MTGJSON repository")
        logger.info("Fetched MTGJSON card data successfully.")
     
        await storage_service.save_with_timestamp(filename= "AllPricesToday.json.xz", data=card_data, file_format="xz")
        logger.info("Stored MTGJSON card data successfully")
    except Exception as e:
        logger.error("Error during MTGJSON data download: %s", e)
        raise
