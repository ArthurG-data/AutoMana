import logging

from automana.core.exceptions.service_layer_exceptions.shop_data_ingestion.shopify import shopify_collection_exception
from automana.core.models.shopify import shopify_theme
from automana.core.repositories.app_integration.shopify.collection_repository import ShopifyCollectionRepository
from automana.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="shop_meta.theme.add",
    db_repositories=["collection"],
)
async def add(collection_repository: ShopifyCollectionRepository, values: shopify_theme.InsertTheme):
    await collection_repository.add_theme(values)
    return {"status": "success", "name": values.name}


@ServiceRegistry.register(
    path="shop_meta.theme.add_collection_theme",
    db_repositories=["collection"],
)
async def add_collection_theme(
    collection_repository: ShopifyCollectionRepository,
    values: shopify_theme.InsertCollectionTheme,
):
    try:
        value = await collection_repository.link_collection_theme(values)
        if not value:
            raise shopify_collection_exception.ShopifyCollectionThemeLinkingError(
                f"Failed to link theme {values.theme_code} to collection {values.collection_name}"
            )
        return value
    except shopify_collection_exception.ShopifyCollectionThemeLinkingError:
        raise
    except Exception as e:
        raise shopify_collection_exception.ShopifyCollectionThemeLinkingError(f"Failed to link theme: {e}")
