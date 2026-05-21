from __future__ import annotations

from uuid import UUID
import logging
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.core.repositories.app_integration.ebay import app_queries
from typing import Optional
from automana.core.repositories.app_integration.ebay import auth_queries
from automana.core.settings import get_settings as get_general_settings

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

    async def update_redirect_uri(self, user_id: str, app_code: str, redirect_uri: str) -> bool:
        result = await self.execute_query(
            app_queries.update_redirect_uri_query,
            (redirect_uri, app_code, user_id)
        )
        return bool(result)
    def delete(self, values):
        raise NotImplementedError("Method 'delete' is not implemented in EbayAccountRepository")

    async def register_app_scopes(
            self, app_id: str, scopes: list[str]
    ):
        await self.execute_command(app_queries.register_app_scopes_query, (app_id, scopes))

    async def link_user_to_app(self, user_id: UUID, app_id: str) -> None:
        await self.execute_command(app_queries.assign_user_app_query, (user_id, app_id))

    async def assign_user_scopes(self, user_id: UUID, app_id: str, scope_urls: list[str]) -> None:
        await self.execute_command(app_queries.assign_user_scopes_query, (user_id, app_id, scope_urls))

    async def list(self):
        raise NotImplementedError("Method 'list' is not implemented in EbayAccountRepository")

    async def get_order_statuses(
        self, app_code: str, order_ids: list[str]
    ) -> dict[str, dict]:
        rows = await self.execute_query(
            app_queries.get_order_statuses_query, (app_code, order_ids)
        )
        return {row["order_id"]: dict(row) for row in (rows or [])}

    async def upsert_order_status(
        self,
        order_id: str,
        app_code: str,
        local_status: str,
        tracking_number: str | None = None,
        carrier_code: str | None = None,
        shipped_at=None,
    ) -> None:
        await self.execute_command(
            app_queries.upsert_order_status_query,
            (order_id, app_code, local_status, tracking_number, carrier_code, shipped_at),
        )
