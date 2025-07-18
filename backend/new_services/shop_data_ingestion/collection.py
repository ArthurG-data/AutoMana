from backend.request_handling.ApiHandler import ApiHandler
from backend.services.shop_data_ingestion.models import shopify_theme

async def add(repository, values: shopify_theme.InsertCollection):
    """Add a collection to the database"""
    await repository.add_collection(values.market_id, values.name)
    return {"status": "success", "name": values.name}

async def link_theme(repository, values: shopify_theme.InsertCollectionTheme):
    """Link a collection to a theme"""
    await repository.link_collection_theme(values.collection_name, values.theme_code)
    return {"status": "success"}
        
            