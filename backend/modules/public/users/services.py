from typing import Annotated
from psycopg2.extensions import connection
from fastapi import  Body, HTTPException, Response
from backend.database.database_utilis import create_insert_query, execute_insert_query, create_update_query, execute_update_query
from backend.modules.public.users.models import  UserUpdatePublic
from backend.modules.auth.models import  BaseUser
from backend.modules.auth.utils import  get_hash_password


def create_user(user : Annotated[BaseUser, Body(
    examples=[
        {
            'username' : 'johnDow',
            'email' : 'johndow@gmail.com',
            'fullname' : 'John Dow',
            'password' : 'password',
        }
    ])], connexion : connection) -> dict:

    hashed_password = get_hash_password(user.hashed_password)
    user.hashed_password = hashed_password
    query = create_insert_query('users', ['username', 'email','fullname', 'hashed_password'], 'unique_id')
    
    values = (user.username, user.email, user.fullname, user.hashed_password)
    try:
        ids = execute_insert_query(connexion,query, values )
        return {'message' : 'user added successfuly', 'ids' : ids}
    except Exception as e:
        raise
     
def update_user(username : str, user : Annotated[UserUpdatePublic, Body(
    examples=[
        {
            'username' : 'johnDow',
            'email' : 'johndow@gmail.com',
            'fullname' : 'John Dow | ',
        }
    ])], connection : connection):

    query = create_update_query('users',['username', 'email','fullname'], ['username = %s'])
    try:
        execute_update_query(connection, query, (user.username, user.email, user.fullname, username), execute_many=False)
        return Response(status_code=204)
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
