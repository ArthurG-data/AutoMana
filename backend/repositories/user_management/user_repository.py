import asyncio
from typing import Optional, Dict, Any
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

    def get_sync(self, username: str) -> dict:
        query = """
        SELECT * FROM users WHERE username = $1;"""
        result = self.execute_query_sync(query, (username,))
        return result[0] if result else None

    async def get_by_id(self, user_id: UUID) -> dict:
        query = """
        SELECT * FROM users WHERE unique_id = $1 AND disabled = FALSE;
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

    async def search_users(
            self,
            username: Optional[str] = None,
            email: Optional[str] = None,
            full_name: Optional[str] = None,
            search_query: Optional[str] = None,
            disabled: Optional[bool] = None,
            #role: Optional[str] = None,
            created_after: Optional[str] = None,
            created_before: Optional[str] = None,
            limit: int = 20,
            offset: int = 0,
            sort_by: str = "username",
            sort_order: str = "asc"
    )-> Dict[str, Any]:
        # Build WHERE conditions
        conditions = []
        values = []
        counter = 1
        
        if username:
            conditions.append(f"username ILIKE ${counter}")
            values.append(f"%{username}%")
            counter += 1
        
        if email:
            conditions.append(f"email ILIKE ${counter}")
            values.append(f"%{email}%")
            counter += 1
        
        if full_name:
            conditions.append(f"fullname ILIKE ${counter}")
            values.append(f"%{full_name}%")
            counter += 1
        
        if search_query:
            conditions.append(f"(username ILIKE ${counter} OR fullname ILIKE ${counter})")
            values.append(f"%{search_query}%")
            counter += 1
        
        if disabled is not None:
            conditions.append(f"disabled = ${counter}")
            values.append(disabled)
            counter += 1
        
        # Add date filters if provided
        if created_after:
            conditions.append(f"created_at >= ${counter}")
            values.append(created_after)
            counter += 1
        
        if created_before:
            conditions.append(f"created_at <= ${counter}")
            values.append(created_before)
            counter += 1
        
        # Build WHERE clause
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # Build ORDER BY clause
        order_clause = f"ORDER BY {sort_by} {sort_order.upper()}"
        
        # Get users
        query = f"""
            SELECT unique_id, username, email, hashed_password, fullname, disabled, created_at, updated_at
            FROM users 
            {where_clause}
            {order_clause}
            LIMIT ${counter} OFFSET ${counter + 1}
        """
        values.extend([limit, offset])
        
        users = await self.execute_query(query, tuple(values))
        
        # Get total count
        count_query = f"""
            SELECT COUNT(*) as total_count 
            FROM users 
            {where_clause}
        """
        count_values = values[:-2]  # Remove limit and offset
        count_result = await self.execute_query(count_query, tuple(count_values))
        total_count = count_result[0]["total_count"] if count_result else 0
        
        return {
            "users": users,
            "total_count": total_count
        }

    async def delete(self, user_id: UUID):
        query = """
        UPDATE users SET deleted_at = NOW(), disabled = TRUE WHERE unique_id = $1;
        """
        result = self.execute_command(query, (user_id,))
        return result

    async def delete_many(self, user_ids: list[UUID]):
        # Implementation of delete_users method
        query = create_delete_query('users', ['unique_id = ANY($1)'])
        await self.execute_command(query, user_ids)

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
    
    
        