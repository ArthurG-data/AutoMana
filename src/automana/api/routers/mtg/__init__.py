from fastapi import APIRouter
from automana.api.routers.mtg.card_reference import card_reference_router
from automana.api.routers.mtg.collection import router as collection_router
from automana.api.routers.mtg.set_reference import router as set_router

mtg_router = APIRouter(prefix="/mtg", tags=["API", "MTG"])

mtg_router.include_router(card_reference_router)
mtg_router.include_router(collection_router)
mtg_router.include_router(set_router)
