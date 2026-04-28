from uuid import UUID
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.database.database_utilis import create_select_query
from datetime import datetime


class SessionRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "SessionRepository"
    async def add(self, values):
         query = """   SELECT user_management.insert_add_token($1, $2, $3, $4, $5, $6, $7, $8, $9);"""
         return await self.execute_command(query, values)

    async def get_all(self):
        query = create_select_query('user_management.v_active_sessions')
        return await self.execute_query(query)

    async def get_many(self, session_id: UUID):
        query = create_select_query('user_management.v_active_sessions', conditions_list=[('session_id = $1 ')])
        return await self.execute_query(query,session_id)

    async def delete(self, ip_address: str, user_id: UUID, session_id: UUID):
        # `user_management.inactivate_session(p_session_id UUID, p_ip_address TEXT)`
        # — 2 args, not 3. `user_id` is kept in the Python signature for the
        # caller's convenience (e.g. authorization checks before calling),
        # but does not map to a SQL parameter.
        query = "SELECT user_management.inactivate_session($1, $2);"
        return await self.execute_query(query, (str(session_id), ip_address))

    async def get_token(self, session_id: UUID):
        query = "SELECT session_id, token_id FROM user_management.v_active_sessions WHERE user_id = $1"
        return await self.execute_query(query, (session_id,))

    async def get(self, session_id: UUID):
        query = "SELECT * FROM user_management.v_active_sessions WHERE session_id = $1"
        return await self.execute_query(query, (session_id,))

    async def get_by_user_id(self, user_id: UUID):
        query = "SELECT * FROM user_management.v_active_sessions WHERE user_id = $1"
        return await self.execute_query(query, (user_id,))

    async def update(self, item):
        raise NotImplementedError("Use rotate_token or invalidate_session for session updates")

    async def rotate_token(self, token_id: UUID, session_id: UUID, refresh_token: str, expire_time: datetime):
        query = 'SELECT user_management.rotate_refresh_token($1, $2, $3, $4);'
        await self.execute_command(query, (token_id, session_id, refresh_token, expire_time))

    async def validate_session_credentials(self, session_id: UUID, ip_address: str, user_agent: str) -> dict:
        query = """
        SELECT *
        FROM user_management.v_active_sessions
        WHERE session_id = $1 AND user_agent = $2 AND ip_address = $3;
        """
        return await self.execute_query(query, (session_id, user_agent, ip_address))

    async def list(self):
        query = "SELECT * FROM user_management.v_active_sessions;"
        return await self.execute_query(query)

    async def invalidate_session(self, session_id: UUID, ip_address: str):
        query = "SELECT user_management.inactivate_session($1, $2)"
        return await self.execute_query(query, (session_id, ip_address))

    async def search(
        self,
        user_id=None,
        username: str = None,
        session_id_filter=None,
        ip_address: str = None,
        user_agent: str = None,
        token_id=None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        conditions = []
        values = []
        counter = 1

        if user_id is not None:
            conditions.append(f"user_id = ${counter}")
            values.append(user_id)
            counter += 1
        if username is not None:
            conditions.append(f"username ILIKE ${counter}")
            values.append(f"%{username}%")
            counter += 1
        if session_id_filter is not None:
            conditions.append(f"session_id = ${counter}")
            values.append(session_id_filter)
            counter += 1
        if ip_address is not None:
            conditions.append(f"ip_address = ${counter}")
            values.append(ip_address)
            counter += 1
        if user_agent is not None:
            conditions.append(f"user_agent ILIKE ${counter}")
            values.append(f"%{user_agent}%")
            counter += 1
        if token_id is not None:
            conditions.append(f"token_id = ${counter}")
            values.append(token_id)
            counter += 1

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"""
            SELECT *, COUNT(*) OVER() AS total_count
            FROM user_management.v_active_sessions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${counter} OFFSET ${counter + 1}
        """
        values.extend([limit, offset])
        rows = await self.execute_query(query, tuple(values))
        total_count = rows[0]["total_count"] if rows else 0
        sessions = [{k: v for k, v in dict(r).items() if k != "total_count"} for r in rows]
        return {"sessions": sessions, "total_count": total_count}
