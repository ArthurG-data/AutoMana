from multiprocessing import connection
from backend.repositories.AbstractRepository import AbstractRepository
from backend.repositories.app_integration.ebay import auth_queries
from backend.schemas.settings import EbaySettings
import urllib, httpx
from uuid import UUID
from pydantic import  HttpUrl
from typing import Optional
from backend.schemas.app_integration.ebay.auth import   ExangeRefreshData, TokenRequestData, TokenResponse

class EbayAuthRepository(AbstractRepository):
    def __init__(self, connection, queryExecutor):
        super().__init__(queryExecutor)
        self.connection = connection

    """Repository for eBay authentication state and token management"""

    @property
    def name(self):
        return "EbayAuthRepository"

    async def log_auth_request(self, request_id: UUID, session_id: UUID, request: HttpUrl, app_id: str) -> UUID:
        """Log an eBay OAuth request"""
        request_id = await self.execute_query(auth_queries.register_oauth_request, (request_id, session_id, request, app_id))
        return request_id if request_id else None

    async def check_auth_request(self, request_id: UUID) -> Optional[tuple]:
        """Check if an eBay OAuth request is valid and return session_id and app_id"""
        row = await self.execute_query(auth_queries.get_valid_oauth_request, request_id)
        session_id = row.get('session_id')
        app_id = row.get('app_id')
        if session_id and app_id:
            return session_id, app_id
        else:
            return None, None


    async def save_refresh_tokens(self, token: TokenResponse, app_id: str, user_id: UUID):
        """Save eBay refresh token to the database"""
        await self.execute_query(auth_queries.assign_refresh_ebay_query, (app_id, app_id, token.refresh_token, token.acquired_on, token.refresh_expires_on, 'refresh_token', user_id))

    async def save_access_token(self, token: TokenResponse, app_id: str, user_id: UUID):
        """Save eBay access token to the database"""
        await self.execute_query(auth_queries.assign_access_ebay_query, (app_id, app_id, token.access_token, token.acquired_on, token.expires_on, 'access_token', user_id))

    async def get_access_from_refresh(self, app_id : str, user_id : UUID):
        """Get access token from refresh token"""
        # check if valide session
        query_2 = """ SELECT token
                    FROM ebay_tokens
                    WHERE app_id = $1 AND used = false AND token_type= 'refresh_token';
                """
        #check if access token is valid wirh session

        row = self.execute_query(self, query_2, app_id)
        refresh_token = row.get('token')
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

    async def get_many(self):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def create(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def update(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")   
    async def delete(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")   
