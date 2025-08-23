from asyncio.log import logger
from multiprocessing import connection
from backend.dependancies.settings import get_general_settings
from backend.repositories.AbstractRepository import AbstractRepository
from backend.repositories.app_integration.ebay import auth_queries
from backend.schemas.settings import EbaySettings
import urllib, httpx
from uuid import UUID
from pydantic import  HttpUrl
from typing import Optional
from backend.schemas.app_integration.ebay.auth import   ExangeRefreshData, TokenRequestData, TokenResponse

class EbayAuthRepository(AbstractRepository):
    def __init__(self, connection, executor: None):
        super().__init__(connection, executor)

    """Repository for eBay authentication state and token management"""

    @property
    def name(self):
        return "EbayAuthRepository"

    def _get_encryption_key(self) ->str:
        key = get_general_settings().pgp_secret_key
        if not key or key == 'fallback-key-change-in-production':
            import warnings
            warnings.warn("Using default encryption key! Set EBAY_ENCRYPTION_KEY environment variable!")
        return key
    
    async def log_auth_request(self
                               , user_id: UUID
                               , app_id : str
                               ) -> UUID:
        """Log an eBay OAuth request"""
        request_id = await self.execute_query(auth_queries.register_oauth_request
                                              , (user_id, app_id, 'pending'))
        return request_id[0].get('unique_id') if request_id else None

    async def check_auth_request(self, request_id: UUID) -> Optional[tuple]:
        """Check if an eBay OAuth request is valid and return session_id and app_id"""
        row = await self.execute_query(auth_queries.get_valid_oauth_request, (request_id,))
        app_id = None
        user_id = None
        app_code = None
        if row and len(row) > 0:
            app_id = row[0].get('app_id')
            user_id = row[0].get('user_id')
            app_code = row[0].get('app_code')
        return app_id , user_id, app_code


    async def save_refresh_tokens(self, token: TokenResponse, app_id: str, user_id: UUID):
        """Save eBay refresh token to the database"""
        await self.execute_query(auth_queries.assign_ebay_token_query, (app_id,  token.refresh_token, token.acquired_on, token.refresh_expires_on, 'refresh_token'))#add user+id next

    async def save_access_token(self, token: TokenResponse, app_id: str, user_id: UUID):
        """Save eBay access token to the database"""
        await self.execute_query(auth_queries.assign_ebay_token_query , (app_id,  token.access_token, token.acquired_on, token.expires_on, 'access_token'))#add user+id next

    async def get_access_from_refresh(self, app_code : str, user_id : UUID):
        """Get access token from refresh token"""
        # check if valide session
        query_2 = """ SELECT et.token
                    FROM ebay_tokens et
                    JOIN app_info ai ON et.app_id = ai.id
                    WHERE ai.app_code = $1 AND et.used = false AND et.token_type= 'refresh_token';
                """
        #check if access token is valid wirh session

        row = await self.execute_query(query_2, (app_code,))
        refresh_token = row[0].get('token')
        return refresh_token if refresh_token else None
   

    async def get_valid_access_token(self, user_id : UUID,app_id : UUID)->str:
        """Get the most recent valid access token for a user and app"""

        query_1 = """ SELECT token
                    FROM ebay_tokens
                    WHERE app_id = $1
                    AND expires_on > now()
                    AND used = false
                    AND token_type = 'access_token'
                    ORDER BY acquired_on DESC
                    LIMIT 1;
                """
        row = await self.execute_query(query_1, app_id)
        return row.get('token') if row else None

    async def check_validity(self, app_id : str, user_id : UUID)->bool:
        token : str = await self.get_valid_access_token(user_id, app_id)
        return token is not None

    async def get_app_settings(self, app_code: str, user_id: UUID):
        query = auth_queries.get_info_login_query()
        encryption_key = self._get_encryption_key()
        settings = await self.execute_query(query, (user_id, app_code, encryption_key))
        return settings[0] if settings else None

    async def get_app_scopes(self,app_id: str) -> list:#needs to be changed later to pick up scopes allowed to a user
        query = auth_queries.get_app_scopes_query
        scopes = await self.execute_query(query, (app_id,))
        return [scope['scope_url'] for scope in scopes] if scopes else []

    async def get(self):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def add(self, item):
        return await super().add(item)
    async def get(self):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def list(self):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def get_many(self):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def create(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def update(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")   
    async def delete(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")   
