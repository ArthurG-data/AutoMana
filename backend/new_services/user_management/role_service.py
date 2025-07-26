from uuid import UUID
from schemas.user_management.role import AssignRoleRequest
from backend.repositories.user_management.role_repository import RoleRepository

async def assign_role(repository: RoleRepository, user_id : UUID,  role : AssignRoleRequest):
    return await repository.assign_role(user_id, role)

from backend.modules.auth.dependancies import currentActiveUser
from backend.database.get_database import cursorDep
from backend.database.database_utilis import execute_select_query
from fastapi import HTTPException, Header
from backend.dependancies import get_internal_settings

def has_role_permission(permission : str):
    """
    Returns a FastAPI dependency that checks if the current user has a specific permission.

    Args:
        permission (str): The required permission name.

    Returns:
        Callable: A dependency function to use in routes.

    Raises:
        HTTPException: If permission is missing or query fails.
    """
    async def checker( user : currentActiveUser, conn : cursorDep):
        query = """ SELECT unique_id FROM user_roles_permission_view WHERE permission = %s AND unique_id = %s """
        try:
            ids = execute_select_query(conn, query, (permission, user.unique_id,), False)
            if ids is None:
                raise HTTPException(status_code=403, detail=f"User lacks '{permission}' permission.")
        except Exception as e:
            raise HTTPException(status_code=500, detail='Error Finding the permission:{e}',)
    return checker()
        

def has_role(role : str):
    """
    Returns a FastAPI dependency that checks if the user has a specific role.

    Args:
        role (str): Role name to verify.

    Returns:
        Callable: A dependency function for FastAPI routes.

    Raises:
        HTTPException: If the role is not found.
    """
    async def checker( conn : cursorDep, user : currentActiveUser):
        query = """ SELECT unique_id FROM user_roles_permission_view WHERE role = %s AND unique_id = %s """
        try:
            ids = execute_select_query(conn, query, (role, user.unique_id,), False)
            if ids is None:
                raise HTTPException(status_code=403, detail=f"User lacks '{role}' permission.")
        except Exception as e:
            raise HTTPException(status_code=500, detail='Error Finding the permission:{e}',)
    return checker

def require_internal_access(x_internal_api_key: str = Header(...)):

    """
    to implement for internal router
    """
    if x_internal_api_key != get_internal_settings():
         raise HTTPException(status_code=403, detail="Unauthorized internal access")
    return True
   