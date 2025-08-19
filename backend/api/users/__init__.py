from fastapi import APIRouter
from backend.api.users.auth import authentification_router
from backend.api.users.session import session_router
from backend.api.users.users import router as users_router

user_router = APIRouter(prefix="/users", tags=["Users"])

user_router.include_router(authentification_router)
user_router.include_router(session_router)
user_router.include_router(users_router)
