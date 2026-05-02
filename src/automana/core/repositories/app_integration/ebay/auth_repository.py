from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.core.repositories.app_integration.ebay import auth_queries
from automana.core.settings import get_settings as get_general_settings
from automana.core.utils.crypto import get_pgp_key


@dataclass
class RefreshTokenRecord:
    refresh_token: str
    expires_at: datetime
    key_version: int


class EbayAuthRepository(AbstractRepository):
    def __init__(self, connection, executor: None):
        super().__init__(connection, executor)

    @property
    def name(self):
        return "EbayAuthRepository"

    # ------------------------------------------------------------------
    # OAuth request log
    # ------------------------------------------------------------------

    async def log_auth_request(self, user_id: UUID, app_id: str) -> UUID:
        rows = await self.execute_query(
            auth_queries.register_oauth_request, (user_id, app_id, "pending")
        )
        return rows[0].get("unique_id") if rows else None

    async def check_auth_request(self, request_id: UUID) -> tuple:
        row = await self.execute_query(auth_queries.get_valid_oauth_request, (request_id,))
        if row:
            return row[0].get("app_id"), row[0].get("user_id"), row[0].get("app_code")
        return None, None, None

    async def get_latest_pending_request(self) -> tuple:
        """Fallback when eBay sandbox drops the state param from the callback."""
        row = await self.execute_query(auth_queries.get_latest_pending_oauth_request, ())
        if row:
            return (
                row[0].get("unique_id"),
                row[0].get("app_id"),
                row[0].get("user_id"),
                row[0].get("app_code"),
            )
        return None, None, None, None

    # ------------------------------------------------------------------
    # Refresh-token persistence (encrypted at rest)
    # ------------------------------------------------------------------

    async def upsert_refresh_token(
        self,
        *,
        user_id: UUID,
        app_id: str,
        refresh_token: str,
        expires_at: datetime,
        key_version: int = 1,
    ) -> None:
        """Encrypt and upsert a refresh token keyed by (user_id, app_id).

        pgp_sym_encrypt runs inside Postgres; the plaintext never appears in
        the query log. The key is bound as a parameter, not interpolated.
        """
        await self.execute_query(
            auth_queries.UPSERT_REFRESH_TOKEN_QUERY,
            (user_id, app_id, refresh_token, get_pgp_key(), expires_at, key_version),
        )

    async def fetch_refresh_token(
        self, *, user_id: UUID, app_code: str
    ) -> Optional[RefreshTokenRecord]:
        """Decrypt and return the stored refresh token under a row-level lock.

        Returns None when no row exists (user has not completed OAuth, or consent
        was revoked). The FOR UPDATE lock serialises concurrent refresh attempts;
        full protection requires an explicit transaction in the caller.
        """
        rows = await self.execute_query(
            auth_queries.FETCH_REFRESH_TOKEN_QUERY,
            (user_id, app_code, get_pgp_key()),
        )
        if not rows:
            return None
        return RefreshTokenRecord(
            refresh_token=rows[0]["refresh_token"],
            expires_at=rows[0]["expires_at"],
            key_version=rows[0]["key_version"],
        )

    # ------------------------------------------------------------------
    # App settings / scopes / environment
    # ------------------------------------------------------------------

    async def get_app_settings(self, app_code: str, user_id: UUID) -> Optional[dict]:
        query = auth_queries.get_info_login_query()
        rows = await self.execute_query(query, (user_id, app_code, get_pgp_key()))
        return rows[0] if rows else None

    def get_app_settings_sync(self, app_code: str, user_id: UUID) -> Optional[dict]:
        query = auth_queries.get_info_login_query()
        rows = self.execute_query_sync(query, (user_id, app_code, get_pgp_key()))
        return rows[0] if rows else None

    async def get_app_scopes(self, app_id: str) -> list:
        rows = await self.execute_query(auth_queries.get_app_scopes_query, (app_id,))
        return [r["scope_url"] for r in rows] if rows else []

    def get_app_scopes_sync(self, app_id: str) -> list:
        rows = self.execute_query_sync(auth_queries.get_app_scopes_query, (app_id,))
        return [r["scope_url"] for r in rows] if rows else []

    async def get_environment(self, app_code: str, user_id: Optional[UUID] = None) -> Optional[str]:
        query = "SELECT environment FROM app_integration.app_info WHERE app_code = $1"
        rows = await self.execute_query(query, (app_code,))
        return rows[0]["environment"] if rows else None

    async def get_env_from_callback(self, state: str, user_id: Optional[UUID] = None) -> Optional[str]:
        query = """
            SELECT ai.environment
              FROM app_integration.log_oauth_request lor
              JOIN app_integration.app_info ai ON lor.app_id = ai.app_id
             WHERE lor.unique_id = $1
        """
        rows = await self.execute_query(query, (state,))
        return rows[0]["environment"] if rows else None

    # ------------------------------------------------------------------
    # AbstractRepository stubs
    # ------------------------------------------------------------------

    async def get(self):
        raise NotImplementedError

    async def add(self, item):
        return await super().add(item)

    async def list(self):
        raise NotImplementedError

    async def get_many(self):
        raise NotImplementedError

    async def create(self, data):
        raise NotImplementedError

    async def update(self, data):
        raise NotImplementedError

    async def delete(self, data):
        raise NotImplementedError
