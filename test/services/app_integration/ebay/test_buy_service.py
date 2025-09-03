from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from backend.exceptions.service_layer_exceptions.app_integration.ebay import ebayBuy_exception
from backend.schemas.app_integration.ebay.listings import ItemModel , BaseCostType    
from backend.new_services.app_integration.ebay.buy import (
    make_active_listing_search,
    get_item_by_id,
    add_item,
    revise_item,
    end_item
)

@pytest.fixture
def get_repo():
    """Fixture for creating a mock EbayBuyRepository"""
    repo = MagicMock()
    repo.get_item = AsyncMock()
    repo.add_item = AsyncMock()
    repo.revise_item = AsyncMock()
    repo.end_item = AsyncMock()
    return repo

@pytest.fixture
def ebay_token():
    """Fixture for eBay API token"""
    return "test-ebay-token"

@pytest.fixture
def ebay_item_test():
    """Fixture for creating a test eBay item"""
    return ItemModel(
        Title="Test Item",
        Description="Test Description",
        PrimaryCategory={
            "CategoryID": "123",
            "CategoryName": "Test Category"
        },
        StartPrice=BaseCostType(currencyID="USD", value="10.00"),
        Quantity=1,
        ListingDuration="Days_7",
        ItemID="123456789"
    )

@pytest.mark.asyncio
async def test_get_listing_by_id_success(get_repo, ebay_item_test, ebay_token):
    """Test getting an item by ID successfully"""
    get_repo.get_item.return_value = ebay_item_test
    item_id = "123456789"
    item = await get_item_by_id(get_repo, ebay_token, item_id)
    assert item == ebay_item_test

@pytest.mark.asyncio
async def test_get_listing_by_id_not_found(get_repo, ebay_token):
    """Test getting an item by ID when it does not exist"""
    get_repo.get_item.return_value = None
    item_id = "nonexistent-id"
    with pytest.raises(ebayBuy_exception.EbayGetItemException):
        await get_item_by_id(get_repo, ebay_token, item_id)
    get_repo.get_item.assert_called_once_with(item_id, ebay_token)

@pytest.mark.asyncio
async def test_add_item_success(get_repo, ebay_item_test, ebay_token):
    """Test adding an item successfully"""
    get_repo.add_item.return_value = ebay_item_test
    item = await add_item(get_repo, ebay_token, ebay_item_test)
    assert item.ItemID == ebay_item_test.ItemID
    get_repo.add_item.assert_called_once_with(ebay_item_test, ebay_token)

@pytest.mark.asyncio
async def test_add_item_failure(get_repo, ebay_item_test, ebay_token):
    """Test adding an item when it fails"""
    get_repo.add_item.return_value = None
    with pytest.raises(ebayBuy_exception.EbayAddItemException):
        await add_item(get_repo, ebay_token, ebay_item_test)
    get_repo.add_item.assert_called_once_with(ebay_item_test, ebay_token)

@pytest.mark.asyncio
async def test_revise_item_success(get_repo, ebay_item_test, ebay_token):
    """Test revising an item successfully"""
    get_repo.revise_item.return_value = ebay_item_test
    item = await revise_item(get_repo, ebay_token, ebay_item_test)
    assert item.ItemID == ebay_item_test.ItemID
    get_repo.revise_item.assert_called_once_with(ebay_item_test, ebay_token)

@pytest.mark.asyncio
async def test_revise_item_failure(get_repo, ebay_item_test, ebay_token):
    """Test revising an item when it fails"""
    get_repo.revise_item.return_value = None
    with pytest.raises(ebayBuy_exception.EbayReviseItemException):
        await revise_item(get_repo, ebay_token, ebay_item_test)
    get_repo.revise_item.assert_called_once_with(ebay_item_test, ebay_token)

@pytest.mark.asyncio
async def test_end_item_success(get_repo, ebay_token):
    """Test ending an item successfully"""
    item_id = "123456789"
    reason = "Item sold"
    get_repo.end_item.return_value = True
    result = await end_item(get_repo, ebay_token, item_id, reason)
    assert result is True
    get_repo.end_item.assert_called_once_with(item_id, reason, ebay_token)

@pytest.mark.asyncio
async def test_end_item_failure_return_none(get_repo, ebay_token):
    """Test ending an item when it fails"""
    item_id = "123456789"
    reason = "Item sold"
    get_repo.end_item.return_value = None
    with pytest.raises(ebayBuy_exception.EbayEndItemException):
        await end_item(get_repo, ebay_token, item_id, reason)
    get_repo.end_item.assert_called_once_with(item_id, reason, ebay_token)

@pytest.mark.asyncio
async def test_end_item_failure_return_false(get_repo, ebay_token):
    """Test ending an item when it fails"""
    item_id = "123456789"
    reason = "Item sold"
    get_repo.end_item.return_value = False
    with pytest.raises(ebayBuy_exception.EbayEndItemException):
        await end_item(get_repo, ebay_token, item_id, reason)
    get_repo.end_item.assert_called_once_with(item_id, reason, ebay_token)
