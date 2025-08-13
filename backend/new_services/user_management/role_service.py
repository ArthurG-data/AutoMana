from uuid import UUID
from backend.schemas.user_management.role import AssignRoleRequest
from backend.repositories.user_management.role_repository import RoleRepository
from backend.schemas.user_management.role import Role
from backend.schemas.user_management import user
from fastapi import HTTPException, Header
from backend.exceptions.service_layer_exceptions.user_management import role_exceptions
from datetime import datetime
#from backend.dependancies import get_internal_settings

async def assign_role(role_repository: RoleRepository
                      , user_id : UUID
                      ,  role : AssignRoleRequest):
    """Assign a role to a user."""
    try:
        existing_role = await role_repository.get_role_by_name(role.role.value)
        if not existing_role:
            raise role_exceptions.RoleNotFoundError(f"Role '{role.role.value}' not found")
        result = await role_repository.assign_role(user_id, role.role.value, role.expires_at, role.effective_from)
        return result
    except role_exceptions.RoleNotFoundError as e:
        raise
    except Exception as e:
        raise role_exceptions.RoleAssignmentError(f"Error assigning role: {e}")

async def revoke_role(role_repository: RoleRepository
                      , user_id: UUID
                      , role_name: Role
                      , revoked_by: UUID):
    """Revoke a role from a user."""
    try:
        result = await role_repository.revoke_role(user_id, role_name=role_name.value, revoked_by=revoked_by)
        return result
    except role_exceptions.RoleNotFoundError as e:
        raise
    except Exception as e:
        raise role_exceptions.RoleRevocationError(f"Error revoking role: {e}")

async def has_role_permission(repository: RoleRepository, permission : str, user : user.UserInDB)->bool:
        try:
            result = await repository.user_has_permission(user.unique_id, permission)
            if result is None or result.get('exists') is False:
                raise role_exceptions.PermissionNotFoundError(f"Permission '{permission}' not found for user {user.unique_id}")
            return True
        except role_exceptions.PermissionNotFoundError:
            raise
        except Exception as e:
            raise role_exceptions.RoleRepositoryError(f"Error checking role permission: {str(e)}")

async def has_role(repository: RoleRepository, role : str,user : user.UserInDB ) -> bool:
        try:
            result = await repository.user_has_role(user.unique_id, role)
            if result is None or result.get('exists') is False:
                raise role_exceptions.RoleNotFoundError(f"Role '{role}' not found for user {user.unique_id}")
            return True
        except role_exceptions.RoleNotFoundError:
            raise
        except Exception as e:
            raise role_exceptions.RoleRepositoryError(f"Error checking role: {str(e)}")