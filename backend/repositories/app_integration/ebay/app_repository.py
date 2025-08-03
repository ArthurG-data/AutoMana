from uuid import UUID
from backend.repositories.AbstractRepository import AbstractRepository
from backend.repositories.app_integration.ebay import app_queries
from typing import Optional
from backend.repositories.app_integration.ebay import auth_queries

class EbayAppRepository(AbstractRepository):
    def __init__(self, connection, queryExecutor):
        super().__init__(queryExecutor)
        self.connection = connection


  
    @property
    def name(self):
        return "EbayAccountRepository"
    
    async def add(self, values : tuple)->bool:
        result = await self.execute_command(app_queries.register_app_query, values)
        return True if result == 1 else False

    async def assign_scope(self, scope : str, app_id : str, user_id : UUID) -> bool | None:
        result = await self.execute_command(app_queries.assign_scope_query, (app_id, scope, user_id))#query needs to be modifies
        return result if result else None
    
    async def get(self, user_id: UUID, app_id: str) -> Optional[dict]:
        """Get eBay app settings for a user"""
        settings = await self.execute_query(auth_queries.get_info_login, (user_id, app_id))
        return settings if settings else None
    
    async def check_app_access(self, user_id: UUID, app_id: str) -> bool:
        """Check if a user has access to a specific eBay app"""
        query = """
                    SELECT EXISTS (
                        SELECT 1
                        FROM ebay_app
                        WHERE user_id = $1 AND app_id = $2
                    );
                """
        return self.execute_query(query, (user_id,app_id))
    
    def get_many(self):
        raise NotImplementedError("Method 'get_many' is not implemented in EbayAccountRepository")
    def create(self, values):
        raise NotImplementedError("Method 'create' is not implemented in EbayAccountRepository")    
    def update(self, values):
        raise NotImplementedError("Method 'update' is not implemented in EbayAccountRepository")    
    def delete(self, values):
        raise NotImplementedError("Method 'delete' is not implemented in EbayAccountRepository")