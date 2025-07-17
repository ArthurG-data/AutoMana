
from backend.services.shop_data_ingestion.models import shopify_models

async def add(repository, values: shopify_models.InsertCollection):
    """Add a collection to the database"""
    await repository.add_collection(values.market_id, values.name)
    return {"status": "success", "name": values.name}

async def link_theme(repository, values: shopify_models.InsertCollectionTheme):
    """Link a collection to a theme"""
    await repository.link_collection_theme(values.collection_name, values.theme_code)
    return {"status": "success"}
        
            