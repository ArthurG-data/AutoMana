import re
from turtle import title
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from backend.new_services.shop_data_ingestion import shopify_collection_service
from backend.schemas.external_marketplace.shopify import shopify_theme
from backend.repositories.shop_meta.shopify_collection_repository import ShopifyCollectionRepository
from backend.exceptions.shop_data_ingestion.shopify import shopify_collection_exception

@pytest.fixture
def mock_repository():
    mock_repository=MagicMock()
    mock_repository.add = AsyncMock()
    mock_repository.get = AsyncMock()
    mock_repository.link_collection_theme = AsyncMock()
    return mock_repository

@pytest.fixture
def mock_insert_collection():
    return shopify_theme.InsertCollection(market_id=1, name="Test Collection")

@pytest.fixture
def mock_insert_collection_theme():
    return shopify_theme.InsertCollectionTheme(collection_name="Test Collection", theme_code="TestTheme")

@pytest.fixture
def mock_collection_theme():
    return shopify_theme.CollectionModel(id=1,
                                         title='Test Collection',
                                         handle ="TestHandle",
                                            description="Test Description",
                                            products_count=10,
                                            published_at="2023-10-01T00:00:00Z",
                                            updated_at="2023-10-01T00:00:00Z")  
                                 

@pytest.mark.asyncio
async def test_add_collection_success(mock_repository, mock_insert_collection, mock_collection_theme):
    mock_repository.get.return_value = mock_collection_theme.model_dump()
    result = await shopify_collection_service.add(mock_repository, mock_insert_collection)
    assert result['title'] == "Test Collection"
    mock_repository.add.assert_called_once_with(mock_insert_collection.market_id, mock_insert_collection.name)

@pytest.mark.asyncio
async def test_add_collection_failure_not_found(mock_repository, mock_insert_collection):
    mock_repository.get.return_value = None
    with pytest.raises(shopify_collection_exception.ShopifyCollectionNotFoundError):
        await shopify_collection_service.add(mock_repository, mock_insert_collection)
    mock_repository.add.assert_called_once_with(mock_insert_collection.market_id, mock_insert_collection.name)

@pytest.mark.asyncio
async def test_add_collection_failure_creation_error(mock_repository, mock_insert_collection):
    mock_repository.add.side_effect = Exception("Database error")
    with pytest.raises(shopify_collection_exception.ShopifyCollectionCreationError):
        await shopify_collection_service.add(mock_repository, mock_insert_collection)
    mock_repository.add.assert_called_once_with(mock_insert_collection.market_id, mock_insert_collection.name)

@pytest.mark.asyncio
async def test_link_theme_success(mock_repository, mock_insert_collection_theme):
    mock_repository.link_collection_theme.return_value = mock_insert_collection_theme.model_dump()
    result = await shopify_collection_service.link_theme(mock_repository, mock_insert_collection_theme)
    assert result['collection_name'] == "Test Collection"
    mock_repository.link_collection_theme.assert_called_once_with(mock_insert_collection_theme.collection_name, mock_insert_collection_theme.theme_code)

@pytest.mark.asyncio
async def test_link_theme_failure(mock_repository, mock_insert_collection_theme):
    mock_repository.link_collection_theme.side_effect = Exception("Linking error")
    with pytest.raises(shopify_collection_exception.ShopifyCollectionThemeLinkingError):
        await shopify_collection_service.link_theme(mock_repository, mock_insert_collection_theme)
    mock_repository.link_collection_theme.assert_called_once_with(mock_insert_collection_theme.collection_name, mock_insert_collection_theme.theme_code)

@pytest.mark.asyncio
async def test_link_theme_failure_not_found(mock_repository, mock_insert_collection_theme):
    mock_repository.link_collection_theme.return_value = None
    with pytest.raises(shopify_collection_exception.ShopifyCollectionThemeLinkingError):
        await shopify_collection_service.link_theme(mock_repository, mock_insert_collection_theme)
    mock_repository.link_collection_theme.assert_called_once_with(mock_insert_collection_theme.collection_name, mock_insert_collection_theme.theme_code)