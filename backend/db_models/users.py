from pydantic import BaseModel, Field, EmailStr
from typing import Annotated
from psycopg2 import IntegrityError
from psycopg2.extensions import connection
from fastapi import  Body, HTTPException
from database import cursorDep, create_insert_query, execute_query
from utils import get_hash_password

class BaseUser(BaseModel):
    username : str = Field(
         title='the user defined username', max_length=50
    )
    email : EmailStr | None = Field(default=None)
    full_name : str | None = Field(
        default=None,title='the user first and last name', max_length=50
    ) 
    
    
    disabled : bool | None = Field(
        default=None, title='Is the user account still active'
    ) 

class UserInDB(BaseUser):
    hashed_password : str 

def create_user(user : Annotated[UserInDB, Body(
    example=[
        {
            'username' : 'johnDow',
            'email' : 'johndow@gmail.com',
            'full_name' : 'John Dow',
            'password' : 'password',
        }
    ])], connexion : connection) -> dict:

    hashed_password = get_hash_password(user.hashed_password)
    query = create_insert_query('users', ['username', 'email','fullname', 'hashed_password'])
    values = [(user.username, user.email, user.full_name, hashed_password)]
    try:
        execute_query(connexion,query, values)
        return {'message' : 'user added successfuly', 'username' : user.username}
    except IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists")
    