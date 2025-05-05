from fastapi import APIRouter,Depends
from backend.authentification import  has_role
from backend.routers.internal import admin_users, admin_sets, admin_collections, admin_sessions
from fastapi.responses import JSONResponse

admin_router = APIRouter(
    prefix='/admin',
    dependencies=[Depends(has_role('admin'))],
    responses={418 :{'description': 'I am an admin'}}
)

admin_router.include_router(admin_users.admin_user_router)
admin_router.include_router(admin_sets.sets_router)
admin_router.include_router(admin_collections.collection_router)
admin_router.include_router(admin_sessions.session_router)

@admin_router.get('/')
async def admin_root():
    return JSONResponse(content="You are an admin, legend.")