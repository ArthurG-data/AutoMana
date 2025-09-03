from backend.repositories.AbstractRepository import AbstractRepository
from backend.repositories.app_integration.ebay.scope_management_repository import scope_queries

class AppIntegrationService(AbstractRepository):
    def __init__(self, connection, executor : None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "AppIntegrationService"

    def add(self, item):
        query =scope_queries.register_scope_query
        return self.execute_command(query, (item.scope_url, item.scope_description))
    
    def update(self, item):
        return super().update(item) 
    def delete(self, item):
        return super().delete(item) 
    def get(self, item_id):
        return super().get(item_id)
