from fastapi import APIRouter
from . import shop_meta, internal_sets_references, internal_card_reference

internal_router = APIRouter(prefix="/internal", tags=["Internal"])

internal_router.include_router(shop_meta.shop_metadata_router)
internal_router.include_router(internal_sets_references.sets_router)
internal_router.include_router(internal_card_reference.router)
