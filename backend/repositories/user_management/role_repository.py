from backend.repositories.AbstractRepository import AbstractRepository
from uuid import UUID

class RoleRepository(AbstractRepository):
    def __init__(self, connection, executor: None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "RoleRepository"
    
    async def assign_role(self, user_id: int, role_name: str):
        query = """INSERT INTO user_roles (user_id, role_id)
            VALUES ($1, (
            SELECT unique_id FROM roles WHERE role = $2))
         """
        query_1 = "SET LOCAL app.current_user_id = $1"
        query_2 = "SET LOCAL app.role_change_reason = $2"
        self.execute_command(query_1, user_id, role_name)
        self.execute_command(query_2, role_name)
        await self.execute_command(query, (user_id, role_name))

    async def get_role_by_name(self, role_name: str):
        query = """SELECT * FROM roles WHERE role = $1"""
        return await self.execute_query(query, role_name)

    async def user_has_permission(self, user_id: UUID, role_name: str) -> dict[str, bool]:
        query = """SELECT EXISTS (
            SELECT unique_id 
            FROM user_roles_permission_view 
            WHERE permission = $1 AND unique_id = $2
        )"""
        return await self.execute_query(query, (user_id, role_name))
    
    async def user_has_role(self, user_id: UUID, role_name: str) -> dict[str, bool]:
        query = """SELECT EXISTS (
            SELECT unique_id 
            FROM user_roles_permission_view 
            WHERE role = $1 AND unique_id = $2
        )"""
        return await self.execute_query(query, (role_name, user_id))
    
    async def get_many(self):
        return NotImplementedError("Method not implemented yet")

    async def delete(self, role_name: str):
        return NotImplementedError("Method not implemented yet")
    async def get(self, role_name: str):
        return NotImplementedError("Method not implemented yet")
    async def update(self, role_name: str):
        return NotImplementedError("Method not implemented yet")
    async def add(self, role_name: str):
        return NotImplementedError("Method not implemented yet")