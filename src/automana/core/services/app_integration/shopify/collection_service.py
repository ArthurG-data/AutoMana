import logging
from typing import List

from automana.core.exceptions.service_layer_exceptions.shop_data_ingestion.shopify import shopify_collection_exception
from automana.core.models.shopify import shopify_theme
from automana.core.repositories.app_integration.shopify.collection_repository import ShopifyCollectionRepository
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="shop_meta.collection.add",
    db_repositories=["collection"],
)
async def add(collection_repository: ShopifyCollectionRepository, values: shopify_theme.InsertCollection):
    try:
        await collection_repository.add(values)
        value = await collection_repository.get(values.name, values.market_id)
        if not value:
            raise shopify_collection_exception.ShopifyCollectionNotFoundError(
                f"Collection {values.name} not found in market {values.market_id}"
            )
        return value
    except shopify_collection_exception.ShopifyCollectionNotFoundError:
        raise
    except Exception as e:
        raise shopify_collection_exception.ShopifyCollectionCreationError(f"Failed to create collection: {e}")


@ServiceRegistry.register(
    path="shop_meta.collection.add_many",
    db_repositories=["collection"],
)
async def add_many(collection_repository: ShopifyCollectionRepository, values: List[shopify_theme.InsertCollection]):
    try:
        await collection_repository.add_many(values)
        return {"status": "success", "count": len(values)}
    except Exception as e:
        raise shopify_collection_exception.ShopifyCollectionCreationError(f"Failed to bulk-insert collections: {e}")
