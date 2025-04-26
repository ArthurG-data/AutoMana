from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import Optional
from uuid import UUID
from enum import Enum
from datetime import datetime, timedelta, timezone



class UserPublic(BaseModel):
    username : str = Field(
         title='the user defined username', max_length=50
    )
    fullname : str | None = Field(
        default=None,title='the user first and last name', max_length=50
    ) 


class BaseUser(UserPublic):
    email : EmailStr | None = Field(default=None)
    hashed_password : str = Field(
        title='Hashed user password'
    )

class UserInDB(BaseUser):
    unique_id : UUID
    disabled : bool | None = Field(
    default=False, title='Is the user account still active'
)
    is_admin : bool =Field(default=False)
    role : str | None=None
    @model_validator(mode='after')
    def validate_role(cls, values):
        values.role = 'admin'  if values.is_admin else  'user'
        return values


class UserUpdatePublic(BaseModel):
    username: str | None=None
    email: str | None=None
    fullname:str | None=None
    hashed_password: str | None=None
 

   
class UserUpdateAdmin(BaseModel):
    disabled : bool | None=None
    is_admin : bool | None = None



class PublicSession(BaseModel):
    user : str = Field(max_length=20)
    expires_at : datetime


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

class CreateSession(BaseModel):
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
    
        
