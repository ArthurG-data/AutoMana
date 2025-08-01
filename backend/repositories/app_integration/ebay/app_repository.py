from uuid import UUID
from backend.repositories.AbstractRepository import AbstractRepository
from backend.repositories.app_integration.ebay import app_queries

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
    
    async def get(self):
        raise NotImplementedError("Method 'get' is not implemented in EbayAccountRepository")
    def get_many(self):
        raise NotImplementedError("Method 'get_many' is not implemented in EbayAccountRepository")
    def create(self, values):
        raise NotImplementedError("Method 'create' is not implemented in EbayAccountRepository")    
    def update(self, values):
        raise NotImplementedError("Method 'update' is not implemented in EbayAccountRepository")    
    def delete(self, values):
        raise NotImplementedError("Method 'delete' is not implemented in EbayAccountRepository")