from fastapi import APIRouter
from automana.api.routers.users.auth import authentification_router
from automana.api.routers.users.session import session_router
from automana.api.routers.users.users import router as users_router

# No tags here — each child router declares its own canonical tag so Swagger
# groups them cleanly without accumulating duplicate tag labels.
user_router = APIRouter(prefix="/users")

user_router.include_router(authentification_router)
user_router.include_router(session_router)
user_router.include_router(users_router)
