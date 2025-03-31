from pydantic import BaseModel, Field, EmailStr
from uuid import UUID

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