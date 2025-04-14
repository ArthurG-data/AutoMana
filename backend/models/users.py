from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone

class BaseUser(BaseModel):
    username : str = Field(
         title='the user defined username', max_length=50
    )
    email : EmailStr | None = Field(default=None)
    fullname : str | None = Field(
        default=None,title='the user first and last name', max_length=50
    ) 
    
    hashed_password : str = Field(
        title='Hashed user password'
    )
    
    disabled : bool | None = Field(
        default=False, title='Is the user account still active'
    ) 



class UserPublic(BaseModel):
    username : str = Field(
         title='the user defined username', max_length=50
    )
    fullname : str | None = Field(
        default=None,title='the user first and last name', max_length=50
    ) 

class UserInDB(BaseUser):
    unique_id : UUID

class UserUpdate(BaseModel):
    username: str | None=None
    email: str | None=None
    fullname:str | None=None

class Session(BaseModel):
    user_id : UUID
    created_at : datetime = Field(default_factory=datetime.now)
    expires_at : Optional[datetime] = None
    ip_address : str = Field(max_length=64)
    user_agent : str
    active : Optional[bool] = None

    @model_validator(mode='after')
    def set_expiry(cls, values):
        if not values.expires_at:
            values.expires_at = values.created_at + timedelta(seconds=7200)
        values.active = values.expires_at > datetime.now(timezone.utc)
        return values
        
