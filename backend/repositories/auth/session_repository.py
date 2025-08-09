from uuid import UUID
from backend.repositories.AbstractRepository import AbstractRepository
from backend.database.database_utilis import create_select_query
from datetime import datetime


class SessionRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "SessionRepository"
    async def add(self, values):
         query = """   SELECT insert_add_token($1, $2, $3, $4, $5, $6, $7, $8, $9);"""
         return await self.execute_command(query, values)
    
    async def get_all(self):
        query = create_select_query('active_sessions_view')
        return await self.execute_query(query)

    async def get_many(self, session_id: UUID):
        query = create_select_query('active_sessions_view', conditions_list=[('session_id = $1 ')])
        return await self.execute_query(query,session_id)

    async def delete( self, ip_address : str, user_id : UUID, session_id : UUID):
        query="SELECT inactivate_session($1, $2, $3);"
        return await self.execute_query(query, (str(session_id), user_id, ip_address))

    async def get_token(self, session_id: UUID):
        query = "SELECT session_id, token_id FROM active_sessions_view WHERE user_id = $1"
        return await self.execute_query(query, (session_id,))

    async def update(self, session_id: UUID, data: dict):
        query = "UPDATE active_sessions_view SET data = $1 WHERE session_id = $2"
        return await self.execute_query(query, (data, session_id))
    
    async def get(self, session_id: UUID):
        query = "SELECT * FROM active_sessions_view WHERE session_id = $1"
        return await self.execute_query(query, (session_id,))

    async def get_by_user_id(self, user_id: UUID):
        query = "SELECT * FROM active_sessions_view WHERE user_id = $1"
        return await self.execute_query(query, (user_id,))

    async def rotate_token(self, token_id: UUID, session_id: UUID, refresh_token: str, expire_time: datetime):
        query = 'SELECT rotate_refresh_token($1, $2, $3, $4);'
        await self.execute_command(query, (token_id, session_id, refresh_token, expire_time))

    async def validate_session_credentials(self, session_id: UUID, ip_address: str, user_agent: str) -> dict:
        query = """
        SELECT refresh_token
        FROM active_sessions_view
        WHERE session_id = $1 AND user_agent = $2 AND ip_address = $3;
        """
        return await self.execute_query(query, (session_id, user_agent, ip_address), select_all=False)
    
    async def list(self):
        query = "SELECT * FROM active_sessions_view;"
        return await self.execute_query(query)

    async def invalidate_session(self, session_id: UUID, ip_address: str):
        query = "SELECT inactivate_session($1, $2)"
        return await self.execute_query(query, (session_id, ip_address))
