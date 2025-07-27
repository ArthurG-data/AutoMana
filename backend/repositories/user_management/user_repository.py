from typing import Optional
from uuid import UUID
from backend.repositories.AbstractRepository import AbstractRepository
from backend.database.database_utilis import create_select_query, create_delete_query

class UserRepository(AbstractRepository):
    def __init__(self, connection, executor : None):
        super().__init__(connection, executor)
    
    @property
    def name(self) -> str:
        return "UserRepository"

    async def add_many(self, values: tuple):
        query = """
        INSERT INTO users (
            username, password, email, first_name, last_name, is_active, is_superuser
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        await self.execute_command(query, values)

    async def get(self, username: str) -> dict:
        condition_lists = ['username = $1']  
        query = create_select_query('users', conditions=condition_lists)
        result = await self.execute_query(query, username)
        return result


    async def get_many(self, usernames: Optional[list[str]], limit: int = 100, offset: int = 0):
        if usernames is None:
            query = """
            SELECT * FROM users
            LIMIT $1 OFFSET $2;
            """
            values = (limit, offset)
        else:
            query = """
            SELECT * FROM users
            WHERE username = ANY($1)
            LIMIT $2 OFFSET $3;
            """
            values = (usernames, limit, offset)

        return await self.execute_query(query, values)

    async def delete_many(self, usernames: list[str]):
        # Implementation of delete_users method
        query = create_delete_query('users', ['username = ANY($1)'])
        await self.execute_command(query, usernames)

    async def update(self, username: str, email: Optional[str], fullname: str):
        return NotImplementedError("Method not implemented yet")

    async def get_user_from_session(self, session_id: UUID)-> dict:
        query = """
     WITH
     get_user_id AS (
     SELECT user_id FROM active_sessions_view WHERE session_id = $1
        )
      SELECT * FROM users WHERE unique_id = (SELECT user_id FROM get_user_id);
    """
        user_data = await self.execute_query(query, session_id)
        return user_data
        