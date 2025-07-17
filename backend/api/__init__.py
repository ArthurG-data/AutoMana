from fastapi import APIRouter
from . import internal , public, auth, ebay

api_router = APIRouter(prefix="/api", tags=["API"])

api_router.include_router(internal.internal_router)
api_router.include_router(public.api_router)
api_router.include_router(auth.authentification_router)
api_router.include_router(ebay.ebay_router)