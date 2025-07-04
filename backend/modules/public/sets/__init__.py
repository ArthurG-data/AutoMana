from fastapi import APIRouter
from backend.modules.public.sets.router import router

sets_router = APIRouter(
        prefix='/sets',
        tags=['sets'], 
        responses={404:{'description':'Not found'}}
        
)

sets_router.include_router(router)