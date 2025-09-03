from typing import List, Optional
from backend.repositories.app_integration.ebay.buy_repository import EbayBuyRepository
from pydantic import BaseModel, Field
from backend.schemas.app_integration.ebay.buy import EbayBrowseSearchParams
from backend.exceptions.service_layer_exceptions.app_integration.ebay import ebayBuy_exception
from backend.exceptions.repository_layer_exceptions import base_repository_exception
from backend.schemas.app_integration.ebay.listings import ItemModel

async def make_active_listing_search(
        repository: EbayBuyRepository,
        token: str,
        search_params: EbayBrowseSearchParams):

    search_params = search_params.to_query_params()

    try:
        response = await repository.make_request(
            endpoint="item_summary/search",
            params=search_params,
        )
        return response
    except Exception as e:
        return {'Error:' : str(e)}
    
async def get_item_by_id(
        repository: EbayBuyRepository,
        token: str,
        item_id: str) -> ItemModel:
    """Get item details by ID"""
    try:
        response = await repository.get_item(item_id, token)
        if not response:
            raise ebayBuy_exception.EbayGetItemException(
                item_id=item_id,
                message="Item not found or retrieval failed"
            )
        return ItemModel.model_validate(response)
    except ebayBuy_exception.EbayGetItemException:
        raise
    except base_repository_exception:
        raise

async def add_item(
        repository: EbayBuyRepository,
        token: str,
        item: ItemModel) -> dict:
    """Add an item to eBay"""
    try:
        response = await repository.add_item(item, token)
        if not response:
            raise ebayBuy_exception.EbayAddItemException(
                item_id=item.ItemID,
                message="Failed to add item"
            )
        return ItemModel.model_validate(response)
    except ebayBuy_exception.EbayAddItemException:
        raise
    except base_repository_exception:
        raise

async def revise_item(
        repository: EbayBuyRepository,
        token: str,
        item: ItemModel) -> dict:
    """Update an existing item on eBay"""
    try:
        response = await repository.revise_item(item, token)
        if not response:
            raise ebayBuy_exception.EbayReviseItemException(
                item_id=item.ItemID,
                message="Failed to revise item"
            )
        return response
    except ebayBuy_exception.EbayReviseItemException:
        raise
    except base_repository_exception:
        raise

async def end_item( 
        repository: EbayBuyRepository,
        token: str,
        item_id: str,
        reason: str) -> bool:
    """End an item listing on eBay"""
    try:
        response = await repository.end_item(item_id, reason, token)
        if not response:
            raise ebayBuy_exception.EbayEndItemException(
                item_id=item_id,
                reason=reason,
                message="Failed to end item"
            )
        return True
    except ebayBuy_exception.EbayEndItemException:
        raise
    except base_repository_exception:
        raise
