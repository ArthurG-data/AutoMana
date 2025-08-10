from fastapi import APIRouter, Depends, HTTPException, Response
from backend.new_services.service_manager import ServiceManager
from backend.schemas.user_management.user import  BaseUser, UserPublic,  UserUpdatePublic
from backend.database.get_database import cursorDep
from backend.dependancies.service_deps import get_current_active_user, get_service_manager
from backend.exceptions import session_exceptions
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/users',
    tags=['users'],
    responses={404:{'description' : 'Not found'}}
)

@router.get('/me', response_model= UserPublic)
async def get_me_user(current_user = Depends(get_current_active_user)):
    try:
        return current_user
    except session_exceptions.SessionAccessDeniedError as e:
        raise HTTPException(status_code=401, detail="Access denied")
    except session_exceptions.SessionUserNotFoundError as e:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post('/')
async def add_user( user: BaseUser
                   , service_manager : ServiceManager = Depends(get_service_manager) ):
    result = await service_manager.execute_service("auth.auth.register", user=user)
    return result

@router.put('/')
async def modify_user( user_update: UserUpdatePublic
                      , service_manager = Depends(get_service_manager)
                      , current_user = Depends(get_current_active_user)):
    result = await service_manager.execute_service("user_management.user.update"
                                                   , user = user_update
                                                   , user_id = current_user.unique_id)
    return result
