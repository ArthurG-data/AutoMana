from pydantic import BaseModel, Field, model_validator, EmailStr
from datetime import datetime, timedelta, timezone
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4


from backend.utilis import now_utc

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
    ip_address : str
    user_agent : str
    expires_on : datetime

class CreateSession(BaseModel):
    session_id :UUID = Field(default_factory=uuid4)
    user_id : UUID
    created_at : datetime = Field(default_factory=now_utc)
    expires_at : Optional[datetime] = None
    ip_address : str = Field(max_length=64)
    refresh_token : str
    refresh_token_expires_at : datetime
    user_agent : str
    active : Optional[bool] = None
    device_id : Optional[UUID] = None

    @model_validator(mode='after')
    def set_expiry_and_active(cls, values):
        if values.expires_at is None:
            # Set default expiry to 2 hours from created_at
            values.expires_at = values.created_at + timedelta(seconds=7200)

        # Set active if expires_at is known
        values.active = values.expires_at > now_utc()
        return values

class PublicSession(BaseModel):
    user : str = Field(max_length=20)
    expires_at : datetime



class Role(str, Enum):
    admin = "admin"
    system = "system"
    developer = "developer"
    tester = "tester"

class AssignRoleRequest(BaseModel):
    role: Role
    reason : Optional[str] = "Assigned via admin endpoint"

