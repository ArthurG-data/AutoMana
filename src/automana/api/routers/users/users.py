from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from automana.api.schemas.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo, ErrorResponse
from automana.api.schemas.user_management.user import BaseUser, UserPublic, UserUpdatePublic, UserInDB, UserAdminPublic
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.dependancies.auth.users import CurrentUserDep, AdminUserDep
from automana.api.schemas.user_management.role import AssignRoleRequest, Role
from automana.api.dependancies.query_deps import (
    sort_params,
    user_search_params,
    pagination_params,
    PaginationParams,
    SortParams,
)
import logging

logger = logging.getLogger(__name__)

_USER_ERRORS = {
    401: {"description": "Not authenticated", "model": ErrorResponse},
    403: {"description": "Insufficient permissions", "model": ErrorResponse},
    422: {"description": "Validation error — malformed or missing fields"},
    500: {"description": "Internal server error", "model": ErrorResponse},
}

router = APIRouter(
    prefix='',
    tags=['Users'],
    responses={404: {'description': 'Not found'}},
)


@router.get(
    '/me',
    summary="Get the currently authenticated user",
    description=(
        "Returns the profile of the currently authenticated user. "
        "Authentication is accepted via the `session_id` cookie or an "
        "`Authorization: Bearer <token>` header. "
        "The response excludes sensitive fields such as `hashed_password`."
    ),
    response_model=UserPublic,
    response_model_exclude_unset=True,
    operation_id="users_get_me",
    responses={
        401: {"description": "Not authenticated — missing or expired session cookie", "model": ErrorResponse},
        **{k: v for k, v in _USER_ERRORS.items() if k not in (401,)},
    },
)
async def get_me(current_user: CurrentUserDep):
    return current_user


@router.get(
    '/',
    summary="Search and list users (paginated)",
    description=(
        "Admin-only. Returns a paginated list of users. Supports filtering by username, "
        "email, or other search fields, plus common sort and pagination controls."
    ),
    response_model=PaginatedResponse[UserAdminPublic],
    operation_id="users_list",
    responses=_USER_ERRORS,
)
async def list_users(
    _admin: AdminUserDep,
    service_manager: ServiceManagerDep,
    pagination: PaginationParams = Depends(pagination_params),
    sorting: SortParams = Depends(sort_params),
    search: dict = Depends(user_search_params),
):
    try:
        result = await service_manager.execute_service(
            "user_management.user.search_users",
            limit=pagination.limit,
            offset=pagination.offset,
            sort_by=sorting.sort_by,
            sort_order=sorting.sort_order,
            **search,
        )
        users = result.get("users", []) if isinstance(result, dict) else []
        total_count = result.get("total_count", 0) if isinstance(result, dict) else len(users)
        return PaginatedResponse(
            success=True,
            data=[UserAdminPublic.model_validate(user) for user in users],
            pagination=PaginationInfo(
                limit=pagination.limit,
                offset=pagination.offset,
                total_count=total_count,
                has_next=pagination.offset + pagination.limit < total_count,
                has_previous=pagination.offset > 0,
            ),
            message=f"Found {len(users)} users",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("user_search_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post(
    '/',
    summary="Register a new user",
    description=(
        "Creates a new user account. Pass the plain-text password in `hashed_password` "
        "— the server hashes it on receipt. Returns the newly created user record "
        "wrapped in an `ApiResponse` envelope."
    ),
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="users_register",
    responses={
        409: {"description": "Username or email already exists"},
        **_USER_ERRORS,
    },
)
async def register_user(user: BaseUser, service_manager: ServiceManagerDep):
    try:
        result = await service_manager.execute_service("auth.auth.register", user=user)
        return ApiResponse(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("user_creation_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.put(
    '/',
    summary="Update the currently authenticated user",
    description=(
        "Updates mutable profile fields (`username`, `email`, `fullname`) for the "
        "user identified by the active session cookie. Partial updates are supported "
        "— only provided fields are changed."
    ),
    response_model=ApiResponse,
    operation_id="users_update_me",
    responses={
        401: {"description": "Not authenticated", "model": ErrorResponse},
        **_USER_ERRORS,
    },
)
async def update_user(
    user_update: UserUpdatePublic,
    service_manager: ServiceManagerDep,
    current_user: CurrentUserDep,
):
    try:
        result = await service_manager.execute_service(
            "user_management.user.update",
            user=user_update,
            user_id=current_user.unique_id,
        )
        return ApiResponse(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("user_update_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.delete(
    '/{user_id}',
    summary="Delete a user by ID",
    description=(
        "Admin-only. Permanently deletes the user account identified by `user_id`. "
        "This action is irreversible. Returns 204 No Content on success."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="users_delete",
    responses={
        404: {"description": "User not found"},
        **_USER_ERRORS,
    },
)
async def delete_user(user_id: UUID, _admin: AdminUserDep, service_manager: ServiceManagerDep):
    try:
        await service_manager.execute_service("user_management.user.delete", user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("user_delete_failed", extra={"error": str(e), "user_id": str(user_id)})
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post(
    '/{user_id}/roles',
    summary="Assign a role to a user",
    description=(
        "Admin-only. Grants the specified role to the target user. "
        "The role assignment can optionally include an expiry date and an "
        "effective-from date."
    ),
    status_code=status.HTTP_201_CREATED,
    operation_id="users_assign_role",
    responses={
        404: {"description": "User not found"},
        409: {"description": "Role already assigned to this user"},
        **_USER_ERRORS,
    },
)
async def assign_role(
    user_id: UUID,
    role: AssignRoleRequest,
    current_user: AdminUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "user_management.user.assign_role",
            role=role,
            user_id=user_id,
            assigned_by=current_user.unique_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("role_assign_failed", extra={"error": str(e), "user_id": str(user_id)})
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.delete(
    '/{user_id}/roles/{role_name}',
    summary="Revoke a role from a user",
    description=(
        "Admin-only. Removes the specified role from the target user. "
        "Returns 204 No Content on success."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="users_revoke_role",
    responses={
        404: {"description": "User or role assignment not found"},
        **_USER_ERRORS,
    },
)
async def revoke_role(
    user_id: UUID,
    role_name: Role,
    current_user: AdminUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        await service_manager.execute_service(
            "user_management.user.revoke_role",
            user_id=user_id,
            role_name=role_name,
            revoked_by=current_user.unique_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("role_revoke_failed", extra={"error": str(e), "user_id": str(user_id)})
        raise HTTPException(status_code=500, detail="Internal Server Error")
