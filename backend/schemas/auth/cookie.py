from typing import List
import base64
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class Cookies(BaseModel):
    session_id : str
    auth : bool
    user : str

class CookiesData(BaseModel):
    session_id : UUID
    ip_address : str
    user_agent : str
    expires_on : datetime

class AccessTokenCookie(BaseModel):
    """Schema for access token cookie data"""
    token: str
    app_code: str
    user_id: str
    expires_at: datetime
    scopes: List[str]

    def to_cookie_value(self) -> str:
        """Convert to secure cookie value"""
        import json
        data = {
            "token": self.token[:10] + "..." + self.token[-10:],  # Truncated for security
            "app_code": self.app_code,
            "user_id": self.user_id,
            "expires_at": self.expires_at.isoformat(),
            "scopes": self.scopes
        }
        return base64.b64encode(json.dumps(data).encode()).decode()
    
class RefreshTokenResponse(BaseModel):
    """Enhanced response for refresh token endpoint"""
    success: bool
    message: str
    access_token: str
    expires_in: int
    expires_on: datetime
    token_type: str = "Bearer"
    scopes: List[str]
    cookie_set: bool = False
    app_code: str
    