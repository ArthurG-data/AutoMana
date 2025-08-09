from pydantic import BaseModel, Field, model_validator
from datetime import datetime, timedelta, timezone
from uuid import UUID

class Token(BaseModel):
    access_token : str
    token_type : str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int

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
