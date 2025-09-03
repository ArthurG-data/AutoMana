from backend.schemas.external_marketplace.shopify import shopify_theme
from backend.exceptions.service_layer_exceptions.shop_data_ingestion.shopify import shopify_collection_exception
from backend.repositories.app_integration.shopify.collection_repository import ShopifyCollectionRepository

async def add(collection_repository: ShopifyCollectionRepository
              , values: shopify_theme.InsertCollection):
    """Add a collection to the database"""
    try:
        await collection_repository.add(values.market_id, values.name)
        value = await collection_repository.get(values.name, values.market_id)
        if not value:
            raise shopify_collection_exception.ShopifyCollectionNotFoundError(f"Collection {values.name} not found in market {values.market_id}")
        return value
    except shopify_collection_exception.ShopifyCollectionNotFoundError:
        raise
    except Exception as e:
        raise shopify_collection_exception.ShopifyCollectionCreationError(f"Failed to create collection: {str(e)}")

async def link_theme(collection_repository: ShopifyCollectionRepository
                     , values: shopify_theme.InsertCollectionTheme):
    """Link a collection to a theme"""
    try:
        value = await collection_repository.link_collection_theme(values.collection_name, values.theme_code)
        if not value:
            raise shopify_collection_exception.ShopifyCollectionThemeLinkingError(f"Failed to link theme {values.theme_code} to collection {values.collection_name}")
        
        return value
    except shopify_collection_exception.ShopifyCollectionThemeLinkingError:
        raise
    except Exception as e:
        raise shopify_collection_exception.ShopifyCollectionThemeLinkingError(f"Failed to link theme: {str(e)}")
