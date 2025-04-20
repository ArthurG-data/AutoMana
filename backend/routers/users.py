
from typing import Annotated
from psycopg2.extensions import connection
from fastapi import  Body, HTTPException, APIRouter, Depends, Response
from backend.database.database_utilis import create_insert_query, execute_insert_query, create_update_query, execute_update_query
from backend.models.users import  BaseUser, UserPublic,  UserUpdatePublic,  UserInDB
from backend.authentification import  get_hash_password, get_current_active_user, check_token_validity
from backend.dependancies import cursorDep


router = APIRouter(
    prefix='/users',
    tags=['users'],
    dependencies=[Depends(check_token_validity)],
    responses={404:{'description' : 'Not found'}}
)

def create_user(user : Annotated[BaseUser, Body(
    examples=[
        {
            'username' : 'johnDow',
            'email' : 'johndow@gmail.com',
            'fullname' : 'John Dow',
            'password' : 'password',
            'is_admin' : 'False'
        }
    ])], connexion : connection) -> dict:

    hashed_password = get_hash_password(user.hashed_password)
    user.hashed_password = hashed_password
    query = create_insert_query('users', ['username', 'email','fullname', 'hashed_password', 'is_admin'])
    
    values = (user.username, user.email, user.fullname, user.hashed_password, user.is_admin)
    try:
        ids = execute_insert_query(connexion,query, values)
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


@router.get('/me', response_model= UserPublic)
async def get_me_user(current_user: UserInDB = Depends(get_current_active_user)):
    return current_user

@router.post('/')
async def add_user( user: BaseUser,  connexion: cursorDep) -> dict:
    return create_user(user, connexion)

@router.put('/')
async def modify_user( user_update: UserUpdatePublic, connection : cursorDep, current_user : UserPublic=Depends(get_current_active_user)):
    return update_user(current_user.username, user_update, connection)