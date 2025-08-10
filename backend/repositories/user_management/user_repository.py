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

    async def add(self, username: str, hashed_password: str, email: str, fullname: str) -> dict:
        query = """
        INSERT INTO users (username, hashed_password, email, fullname)
        VALUES ($1, $2, $3, $4)
        RETURNING *;
        """
        values = (username, hashed_password, email, fullname)
        result = await self.execute_query(query, values)
        return result[0] if result else None
    
    async def get(self, username: str) -> dict:
        query = """
        SELECT * FROM users WHERE username = $1;"""
        result = await self.execute_query(query, (username,))
        return result[0] if result else None
    
    async def get_by_id(self, user_id: UUID) -> dict:
        query = """
        SELECT * FROM users WHERE unique_id = $1;
        """
        result = await self.execute_query(query, (user_id,))
        return result[0] if result else None

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

    async def delete(self, user_id: UUID):
        query = """
        DELETE FROM users WHERE unique_id = $1;
        """
        await self.execute_command(query, user_id)

    async def delete_many(self, usernames: list[str]):
        # Implementation of delete_users method
        query = create_delete_query('users', ['username = ANY($1)'])
        await self.execute_command(query, usernames)

    async def update(self, user_id: UUID, username: Optional[str], email: Optional[str], fullname: Optional[str]):
        query = "UPDATE users SET"
        values = []
        counter = 1
        update_statements = []
        if username is not None:
            update_statements.append(f" username = ${counter}")
            values.append(username)
            counter += 1
        if email is not None:
            update_statements.append(f" email = ${counter}")
            values.append(email)
            counter += 1
        if fullname is not None:
            update_statements.append(f" fullname = ${counter}")
            values.append(fullname)
        query += ", ".join(update_statements)
        query += f" WHERE unique_id = ${counter + 1} RETURNING *;"
        values.append(user_id)
        result = await self.execute_query(query, values)
        return result[0] if result else None

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
    
    async def list(self):
        raise NotImplementedError("Method not implemented yet")
        