from fastapi import APIRouter
from backend.modules.public.auth.routers import authentification_router


auth_router =  APIRouter(prefix = '/auth', tags=['auth'])

auth_router.include_router(authentification_router)