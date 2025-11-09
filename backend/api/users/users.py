
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from backend.new_services.service_manager import ServiceManager
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from backend.schemas.user_management.user import  BaseUser, UserPublic,  UserUpdatePublic, UserInDB
from backend.dependancies.service_deps import get_current_active_user, get_service_manager
from backend.exceptions import session_exceptions
from backend.schemas.user_management.role import AssignRoleRequest, Role
from backend.dependancies.query_deps import (sort_params
                                             ,user_search_params
                                             ,pagination_params
                                             ,PaginationParams
                                             ,SortParams)
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
        return ApiResponse(data=current_user)
    except session_exceptions.SessionAccessDeniedError as e:
        raise HTTPException(status_code=401, detail="Access denied")
    except session_exceptions.SessionUserNotFoundError as e:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get('/', response_model=PaginatedResponse[UserInDB])
async def get_users(
    service_manager: ServiceManager = Depends(get_service_manager),
    pagination: PaginationParams = Depends(pagination_params),
    sorting: SortParams = Depends(sort_params),
    search: dict = Depends(user_search_params)
    ):
    try:
        result = await service_manager.execute_service("user_management.user.search_users",
                                                    limit=pagination.limit,
                                                    offset=pagination.offset,
                                                    sort_by=sorting.sort_by,
                                                    sort_order=sorting.sort_order,
                                                    **search)
        users = result.get("users", []) if isinstance(result, dict) else []
        total_count = result.get("total_count", 0) if isinstance(result, dict) else len(users)
        return PaginatedResponse(
                success=True,
                data=[UserInDB.model_validate(user) for user in users],
                pagination=PaginationInfo(
                    limit=pagination.limit,
                    offset=pagination.offset,
                    total_count=total_count,
                    has_next=pagination.offset + pagination.limit < total_count,
                    has_previous=pagination.offset > 0
                ),
                message=f"Found {len(users)} users"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching users: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post('/')
async def add_user( user: BaseUser
                   , service_manager : ServiceManager = Depends(get_service_manager) ):
    print(user)
    try:
        result = await service_manager.execute_service("auth.auth.register", user=user)
        return ApiResponse(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding user: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.put('/')
async def modify_user( user_update: UserUpdatePublic
                      , service_manager = Depends(get_service_manager)
                      , current_user = Depends(get_current_active_user)):
    try:
        result = await service_manager.execute_service("user_management.user.update"
                                                       , user = user_update
                                                       , user_id = current_user.unique_id)
        return ApiResponse(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error modifying user: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.delete('/{user_id}', status_code=204)
async def delete_user(user_id: UUID, service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service("user_management.user.delete_user", user_id=user_id)
        return ApiResponse(data=None)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post('/{user_id}/roles', status_code=status.HTTP_201_CREATED)
async def assign_role(user_id: UUID
                      , role: AssignRoleRequest
                      , current_user = Depends(get_current_active_user)
                      , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service("user_management.user.assign_role"
                                              , role=role
                                              , user_id=user_id
                                              , assigned_by=current_user.unique_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning role to user: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.delete('/{user_id}/roles/{role_name}', status_code=status.HTTP_204_NO_CONTENT)
async def revoke_role(user_id: UUID
                      , role_name: Role
                      , current_user = Depends(get_current_active_user)
                      , service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service("user_management.user.revoke_role"
                                              , user_id=user_id
                                              , role_name=role_name
                                              , revoked_by=current_user.unique_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking role from user: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")