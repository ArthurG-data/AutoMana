from backend.repositories.AbstractRepository import AbstractRepository

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
        return NotImplementedError("Method not implemented yet")

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