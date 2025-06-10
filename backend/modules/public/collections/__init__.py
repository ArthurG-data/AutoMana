from fastapi import APIRouter
from backend.modules.public.collections.router import router

collection_router = APIRouter(
    prefix='/collection',
    tags=['collection'],
    responses={404:{'description':'Not found'}}
)

collection_router.include_router(router)
