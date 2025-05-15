from fastapi import APIRouter
from backend.routers.sets.router import router

sets_router = APIRouter(
        prefix='/sets',
        tags=['sets'], 
        responses={404:{'description':'Not found'}}
        
)

sets_router.include_router(router)