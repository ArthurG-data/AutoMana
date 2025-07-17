from fastapi import APIRouter, Request
from typing import List
from backend.dependancies import ipDep
from backend.database.get_database import cursorDep
from backend.modules.public.users.models import AdminReturnSession
from uuid import UUID
#from backend.utilis import extract_ip
from backend.modules.auth.dependancies import currentActiveUser
from backend.modules.admin import admin_sessions_services


session_router = APIRouter(
    prefix='/session',
    tags=['admin-sessions']
)

@session_router.get('/', response_model=List[AdminReturnSession])
async def get_sessions(conn: cursorDep):
    return await admin_sessions_services.get_sessions(conn)
 
@session_router.get('/{session_id}/', response_model= AdminReturnSession)
async def get_sessions(conn: cursorDep, session_id : UUID):
    return await admin_sessions_services.get_sessions(conn, session_id)

@session_router.delete('/{session_id}/desactivate')
async def delete_session(conn : cursorDep, ip_address : ipDep, current_user : currentActiveUser, request : Request, session_id : UUID):
    await admin_sessions_services.delete_session(conn, ip_address, current_user, request, session_id)