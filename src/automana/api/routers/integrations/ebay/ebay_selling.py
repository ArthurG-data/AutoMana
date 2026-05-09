from automana.core.models.ebay import listings as listings_model
from fastapi import APIRouter, HTTPException, Query, Header, UploadFile, File
from pydantic import BaseModel
from typing import Annotated, Any, Dict, Optional
from uuid import UUID
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.dependancies.auth.users import CurrentUserDep
from automana.api.schemas.StandardisedQueryResponse import (
    ApiResponse,
    PaginatedResponse,
    PaginationInfo,
)


class BuildListingRequest(BaseModel):
    card_version_id: UUID
    condition: str
    quantity: int
    price_aud: str
    foil: bool = False
    lang: str = "en"
    shipping_cost_aud: str = "0.00"
    condition_note: Optional[str] = None
    description_mode: str = "full"
    brand_config: Optional[Dict[str, Any]] = None
    marketplace_id: str = "15"

ebay_listing_router = APIRouter(prefix='/listing', tags=['listings'])


@ebay_listing_router.post("/", description="Post a new listing")
async def create_listing(
    listing: listings_model.ItemModel,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.listings.create",
            user_id=user.unique_id,
            app_code=app_code,
            item=listing,
            idempotency_key=idempotency_key,
        )
        return ApiResponse(data=result, message="Listing created successfully")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@ebay_listing_router.post("/from-card", description="Build and post a listing from a card version")
async def build_and_create_listing(
    body: BuildListingRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.listings.build_and_create",
            user_id=user.unique_id,
            app_code=app_code,
            card_version_id=body.card_version_id,
            condition=body.condition,
            quantity=body.quantity,
            price_aud=body.price_aud,
            foil=body.foil,
            lang=body.lang,
            shipping_cost_aud=body.shipping_cost_aud,
            condition_note=body.condition_note,
            description_mode=body.description_mode,
            brand_config=body.brand_config,
            marketplace_id=body.marketplace_id,
            idempotency_key=idempotency_key,
        )
        return ApiResponse(data=result, message="Listing created successfully")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@ebay_listing_router.get("/active", description="Get the active listings of a user")
async def get_active_listings(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
    limit: Annotated[int, Query(gt=0, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        result: listings_model.PaginatedListings = await service_manager.execute_service(
            "integrations.ebay.selling.listings.active",
            user_id=user.unique_id,
            app_code=app_code,
            limit=limit,
            offset=offset,
        )
        return PaginatedResponse(
            message="Active listings retrieved successfully",
            data=result.items,
            pagination=PaginationInfo(
                limit=limit,
                offset=offset,
                total_count=result.total if result.total is not None else len(result.items),
                has_next=result.has_more,
                has_previous=offset > 0,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@ebay_listing_router.get("/history", description="Get the order fulfillment history")
async def get_order_history(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
    limit: Annotated[int, Query(gt=0, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        result: listings_model.PaginatedOrders = await service_manager.execute_service(
            "integrations.ebay.selling.fulfillment.history",
            user_id=user.unique_id,
            app_code=app_code,
            limit=limit,
            offset=offset,
        )
        return PaginatedResponse(
            message="Order history retrieved successfully",
            data=result.items,
            pagination=PaginationInfo(
                limit=limit,
                offset=offset,
                total_count=result.total if result.total is not None else len(result.items),
                has_next=result.has_more,
                has_previous=offset > 0,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@ebay_listing_router.put("/{item_id}", description="Update an existing listing")
async def update_listing(
    updated_item: listings_model.ItemModel,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    item_id: str,
    app_code: str = Query(..., description="eBay application code"),
):
    if updated_item.ItemID != item_id:
        raise HTTPException(status_code=400, detail="Item ID in URL and body must match")
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.listings.update",
            user_id=user.unique_id,
            app_code=app_code,
            item=updated_item,
        )
        return ApiResponse(data=result, message="Listing updated successfully")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@ebay_listing_router.delete("/{item_id}", description="End an existing listing")
async def end_listing(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    item_id: str,
    app_code: str = Query(..., description="eBay application code"),
    ending_reason: Optional[str] = Query(None, description="Reason for ending the listing"),
):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.listings.end",
            user_id=user.unique_id,
            app_code=app_code,
            item_id=item_id,
            ending_reason=ending_reason or "NotAvailable",
        )
        return ApiResponse(data=result, message="Listing ended successfully")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@ebay_listing_router.post("/upload-picture", description="Upload an image to eBay's picture hosting")
async def upload_listing_picture(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    file: UploadFile = File(...),
    app_code: str = Query(..., description="eBay application code"),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (image/* content type required)")
    file_bytes = await file.read()
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.listings.upload_picture",
            user_id=user.unique_id,
            app_code=app_code,
            file_bytes=file_bytes,
            content_type=file.content_type,
        )
        return ApiResponse(data=result, message="Picture uploaded successfully")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
