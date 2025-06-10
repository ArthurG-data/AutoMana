from fastapi import APIRouter,Depends
from backend.modules.internal.sets import router
from backend.modules.security.authorisation import  has_role
from backend.modules.admin import admin_users, admin_collections, admin_sessions, admin_ebay
from fastapi.responses import JSONResponse

admin_router = APIRouter(
    prefix='/admin',
    dependencies=[Depends(has_role('admin'))],
    responses={418 :{'description': 'I am an admin'}}
)

admin_router.include_router(admin_users.admin_user_router)
admin_router.include_router(router.sets_router)
admin_router.include_router(admin_collections.collection_router)
admin_router.include_router(admin_sessions.session_router)
admin_router.include_router(admin_ebay.admin_ebay_router)

@admin_router.get('/')
async def admin_root():
    return JSONResponse(content="You are an admin, legend.")