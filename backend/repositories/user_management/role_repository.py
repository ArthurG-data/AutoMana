from datetime import datetime
from typing import Optional
from backend.repositories.AbstractRepository import AbstractRepository
from uuid import UUID
from typing import Optional
from backend.schemas.user_management.role import Role

class RoleRepository(AbstractRepository):
    def __init__(self, connection, executor: None):
            super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "RoleRepository"

    async def assign_role(self
                          , user_id: int
                          , role_name: Role
                          , reason: Optional[str]
                          , assigned_by: UUID
                          , expires_at: Optional[datetime]=None
                          , effective_from: Optional[datetime]=None):

        query = """INSERT INTO user_roles (user_id, role_id, expires_at, effective_from)
            VALUES ($1, (
            SELECT unique_id FROM roles WHERE role = $2), $3, $4)
         """
        set_user_query = f"SET LOCAL app.current_user_id = '{assigned_by}';"
        set_reason_query = f"SET LOCAL app.role_change_reason = '{reason}';"
        await self.execute_command(set_user_query)
        await self.execute_command(set_reason_query)
        await self.execute_command(query, (user_id, role_name, expires_at, effective_from))

    async def revoke_role(self
                          , user_id: int
                          , role_name: Role
                          , revoked_by: UUID):
        query = """DELETE FROM user_roles WHERE user_id = $1 AND role_id = (
            SELECT unique_id FROM roles WHERE role = $2
        )"""
        set_user_query = f"SET LOCAL app.current_user_id = '{revoked_by}';"
        await self.execute_command(set_user_query)
        await self.execute_command(query, (user_id, role_name))

    async def get_role_by_name(self, role_name: Role):
        query = """SELECT * FROM roles WHERE role = $1"""
        return await self.execute_query(query, (role_name,))

    async def user_has_permission(self, user_id: UUID, role_name: Role) -> dict[str, bool]:
        query = """SELECT EXISTS (
            SELECT unique_id 
            FROM user_roles_permission_view 
            WHERE permission = $1 AND unique_id = $2
        )"""
        return await self.execute_query(query, (user_id, role_name))
    
    async def user_has_role(self, user_id: UUID, role_name: Role) -> dict[str, bool]:
        query = """SELECT EXISTS (
            SELECT unique_id 
            FROM user_roles_permission_view 
            WHERE role = $1 AND unique_id = $2
        )"""
        return await self.execute_query(query, (role_name, user_id))
    
    async def get_many(self):
        return NotImplementedError("Method not implemented yet")


    async def delete(self, role_name: Role):
        query = """DELETE FROM roles WHERE role = $1"""
        return await self.execute_command(query, (role_name,))

    async def get(self, role_name: Role):
        query = """SELECT * FROM roles WHERE role = $1"""
        return await self.execute_query(query, (role_name,))

    async def update(self, role_name: Role):
        query = """UPDATE roles SET role = $1 WHERE role = $2"""
        return await self.execute_command(query, (role_name, role_name))
    async def add(self, role_name: str):
        return NotImplementedError("Method not implemented yet")
    async def list(self):
        return NotImplementedError("Method not implemented yet")