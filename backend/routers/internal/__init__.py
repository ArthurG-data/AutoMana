from fastapi import APIRouter, HTTPException, Depends
from backend.authentification import decode_access_token, get_token_from_header_or_cookie
from backend.routers.internal import admin_users, admin_sets
from fastapi.responses import JSONResponse

async def admin_required(token: str = Depends(get_token_from_header_or_cookie)):
        payload = decode_access_token(token)
        if payload.get('role') != 'admin':
            raise HTTPException(status_code=400, detail='You are not an admin')

admin_router = APIRouter(
    prefix='/admin',
    dependencies=[Depends(admin_required)],
    responses={418 :{'description': 'I am an admin'}}
)

admin_router.include_router(admin_users.admin_user_router)
admin_router.include_router(admin_sets.sets_router)

@admin_router.get('/')
async def admin_root():
    return JSONResponse(content="You are an admin, legend.")