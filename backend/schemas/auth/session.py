from pydantic import BaseModel, Field, model_validator
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4
from backend.utilis import now_utc

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

