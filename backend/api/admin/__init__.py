from fastapi import APIRouter
from . import admin_card_reference, admin_collection, admin_session, admin_users
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

admin_router.include_router(admin_card_reference.router)
admin_router.include_router(admin_collection.collection_router)
admin_router.include_router(admin_session.session_router)
admin_router.include_router(admin_users.admin_user_router)