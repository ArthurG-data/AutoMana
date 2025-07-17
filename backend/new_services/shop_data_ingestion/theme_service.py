from backend.services.shop_data_ingestion.models import shopify_models

async def add(repository, values: shopify_models.InsertTheme):
    """Add a theme to the database"""
    await repository.add_theme(values)
    return {"status": "success", "name": values.name}