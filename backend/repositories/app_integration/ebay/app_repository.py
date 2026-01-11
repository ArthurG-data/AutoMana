from uuid import UUID
import logging
from backend.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from backend.repositories.app_integration.ebay import app_queries
from typing import Optional
from backend.repositories.app_integration.ebay import auth_queries
from backend.core.settings import get_settings as get_general_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EbayAppRepository(AbstractRepository):
    def __init__(self, connection, executor : None):
        super().__init__(connection, executor)

    @property
    def name(self):
        return "EbayAccountRepository"

    def _get_encryption_key(self) ->str:
        key = get_general_settings().pgp_secret_key
        if not key or key == 'fallback-key-change-in-production':
            import warnings
            warnings.warn("Using default encryption key! Set EBAY_ENCRYPTION_KEY environment variable!")
        return key

    async def add(self, values: tuple) -> bool:
        list_values = list(values)
        list_values.append(self._get_encryption_key())
        input = tuple(list_values)
        result = await self.execute_query(app_queries.register_app_query
                                            , input)
        logger.info(f"App registration result: {result}")
        return result[0]['app_code'] if result else None

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

    async def register_app_scopes(
            self, app_id: str, scopes: list[str]
    ):
        await self.execute_command(app_queries.register_app_scopes_query, (app_id, scopes))

    async def list(self):
        raise NotImplementedError("Method 'list' is not implemented in EbayAccountRepository")