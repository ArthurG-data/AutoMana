from pydantic import BaseModel, Field, EmailStr

class BaseUser(BaseModel):
    username : str = Field(
         title='the user defined username', max_length=50
    )
    email : EmailStr | None = Field(default=None)
    fullname : str | None = Field(
        default=None,title='the user first and last name', max_length=50
    ) 
    
    
    disabled : bool | None = Field(
        default=None, title='Is the user account still active'
    ) 



class UserPublic(BaseModel):
    username : str = Field(
         title='the user defined username', max_length=50
    )
    fullname : str | None = Field(
        default=None,title='the user first and last name', max_length=50
    ) 

class UserInDB(BaseUser):
    hashed_password : str

class UserUpdate(UserInDB):
    username: str | None=None
    email: str | None=None
    fullname:str | None=None
    hashed_password : str | None=None
    disabled : bool | None=None