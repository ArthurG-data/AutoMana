from fastapi import APIRouter
from backend.routers.users.routers import router 

user_router = APIRouter(
    prefix='/users',
    tags=['users'],
    responses={404:{'description' : 'Not found'}}
)

user_router.include_router(router)