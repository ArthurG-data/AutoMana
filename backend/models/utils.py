from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from datetime import datetime, timedelta, timezone

class Token(BaseModel):
    access_token : str
    token_type : str

class TokenData(BaseModel):
    sub : str | None=None
    id : UUID
    role : str
    exp : int

class PublicTokenData(BaseModel):
    sub : str
    id : UUID
    exp : int = Field(exclude=True)
    is_expired : bool = Field(default=True)
    @model_validator(mode='after')
    def check_expiry(cls, values):
        if datetime.now(timezone.utc) < datetime.now(timezone.utc) + timedelta(seconds=values.exp):
            values.is_expired = False
        return values

class Cookies(BaseModel):
    session_id : str
    auth : bool
    user : str

class CookiesData(BaseModel):
    session_id : UUID
    refresh_token_id : UUID
    ip_address : str
    user_agent : str