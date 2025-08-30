from backend.schemas.external_marketplace.shopify import shopify_theme

async def add(repository, values: shopify_theme.InsertTheme):
    """Add a theme to the database"""
    await repository.add_theme(values)
    return {"status": "success", "name": values.name}