from fastapi import APIRouter
from automana.api.routers.mtg.card_reference import card_reference_router
from automana.api.routers.mtg.collection import router as collection_router
from automana.api.routers.mtg.set_reference import router as set_router

# No tags here — each child router declares its own canonical tag ("Card Catalogue",
# "Collections") so Swagger groups them cleanly without accumulating duplicates.
mtg_router = APIRouter(prefix="/mtg")

mtg_router.include_router(card_reference_router)
mtg_router.include_router(collection_router)
mtg_router.include_router(set_router)
