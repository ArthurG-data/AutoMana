
from fastapi import APIRouter
from backend.routers.auth.routers import authentification_router 


router = APIRouter(
    prefix='/auth',
    tags=['authentificate'])

router.include_router(authentification_router)