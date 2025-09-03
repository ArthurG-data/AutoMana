from fastapi import APIRouter
from backend.api.catalog.mtg.card_reference import card_reference_router
from backend.api.catalog.mtg.collection import router as collection_router
from backend.api.catalog.mtg.set_reference import router as set_router

mtg_router = APIRouter(prefix="/mtg", tags=["API", "MTG"])

mtg_router.include_router(card_reference_router)
mtg_router.include_router(collection_router)
mtg_router.include_router(set_router)
