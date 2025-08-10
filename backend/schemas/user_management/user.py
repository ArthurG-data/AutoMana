from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import Optional
from uuid import UUID, uuid4
from enum import Enum
from datetime import datetime, timedelta
from backend.utilis import now_utc

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
    created_at : Optional[datetime]=None
   
class UserUpdatePublic(BaseModel):
    username: str | None=None
    email: str | None=None
    fullname:str | None=None
 
class UserUpdateAdmin(BaseModel):
    disabled : bool | None=None

class AdminReturnSession(BaseModel):
    username : str
    session_id : UUID
    session_expires_at : datetime
