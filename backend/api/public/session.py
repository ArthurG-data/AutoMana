from fastapi import APIRouter, Request, Depends, Response, HTTPException
from typing import List
from backend.dependancies import ipDep
from backend.schemas.user_management.user import AdminReturnSession
from uuid import UUID
#from backend.utilis import extract_ip
from backend.dependancies.service_deps import get_service_manager, get_current_active_user
from backend.new_services.service_manager import ServiceManager

from backend.dependancies.query_deps import (
    session_search_params,
    pagination_params,
    sort_params,
    date_range_params,
    PaginationParams,
    SortParams,
    DateRangeParams
)

session_router = APIRouter(
    prefix='/session',
    tags=['sessions']
)

@session_router.get('/', response_model=List[AdminReturnSession])
async def get_sessions(
                       search_params: dict = Depends(session_search_params),
                       pagination: PaginationParams = Depends(pagination_params),
                       sorting: SortParams = Depends(sort_params),
                       date_range: DateRangeParams = Depends(date_range_params),
                       service_manager: ServiceManager = Depends(get_service_manager)
                       ):
    try:
        return await service_manager.execute_service(
            "auth.session.search_sessions",
            search_params=search_params,
            pagination=pagination,
            sorting=sorting,
            date_range=date_range
        )
    except HTTPException:
        raise
    except Exception: 
        raise HTTPException(status_code=500, detail="Internal Server Error")

@session_router.get('/{session_id}/', response_model= AdminReturnSession)
async def get_sessions(conn: cursorDep, session_id : UUID):
    return await admin_sessions_services.get_sessions(conn, session_id)

@session_router.delete('/{session_id}/desactivate')
async def delete_session(conn : cursorDep, ip_address : ipDep, current_user : currentActiveUser, request : Request, session_id : UUID):
    await admin_sessions_services.delete_session(conn, ip_address, current_user, request, session_id)