
from typing import Annotated,  Union, Optional, List
from psycopg2 import IntegrityError, Error
from psycopg2.extensions import connection
from fastapi import  Body, HTTPException, APIRouter, Depends, status, Query, Response

from backend.database import create_insert_query, execute_query,create_select_query
from backend.dependancies import get_token_header, cursorDep
from backend.models.users import  BaseUser, UserPublic, UserInDB, UserUpdate
from backend.authentification import get_current_active_user, get_hash_password, get_user



router = APIRouter(
    prefix='/users',
    tags=['users'],
    dependencies=[Depends(get_token_header)],
    responses={404:{'description' : 'Not found'}}
)


def create_user(user : Annotated[UserInDB, Body(
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
    query = create_insert_query('users', ['username', 'email','fullname', 'hashed_password'])
   
    values = (user.username, user.email, user.fullname, user.hashed_password)
    try:
        execute_query(connexion,query, values)
        return {'message' : 'user added successfuly', 'username' : user.username}
    except IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists")
    
def get_user(username : str, connection : connection) -> UserPublic:
    query = create_select_query('users', where_columns=['username'])
    try:
        user = execute_query(connection, query, (username,), fetch=True)[0]
        if not user:
            raise HTTPException(status_code=404, detail='User not found')
        return UserPublic.model_validate(user) 
    except HTTPException as e:
        raise e 

    except Error as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {db_err}") 

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
   
def get_users(usernames : Optional[list[str]], limit : int, offset :int, connection : connection) -> list[UserPublic]:

    query = "SELECT * FROM users WHERE username = ANY(%s) LIMIT %s OFFSET %s;"
    values =  (usernames , limit, offset)
    try:
        users = execute_query(connection, query, values, fetch=True)
        if not users:
            raise HTTPException(status_code=404, detail='Users not found')
       
        return [UserPublic.model_validate(user) for user in users]
    except HTTPException as e:
        raise e 

    except Error as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {db_err}") 

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

def delete_users(usernames : list[str], connection : connection) :
    query = """ DELETE FROM users WHERE username = ANY(%s); """
    try:
        execute_query(connection, query, (usernames,), execute_many=False)
        return Response(status_code=204)
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# need to be completed
def update_user(user : Annotated[UserUpdate, Body(
    examples=[
        {
            'username' : 'johnDow',
            'email' : 'johndow@gmail.com',
            'fullname' : 'John Dow | ',
            'hashed_passwod' : 'new_password'
        }
    ])], connection : connection):
    query = """ UPDATE users SET username = %s, email = %s, fullname = %s, hashed_password = %s; """
    
@router.get('/{username}', response_model=UserPublic) 
async def user_endpoint( connection : cursorDep, username : str):
    return get_user(username, connection)

@router.delete('/')
async def delete_user(connection : cursorDep, username : Annotated[list[str] , Query(title='Query string')] = None):
    try:
        return(delete_users(username, connection))
    except Exception:
        raise

@router.get('/', response_model=List[UserPublic]) 
async def user_endpoints( connection : cursorDep,
                        limit : Annotated[int, Query(le=100)]=100,
                        offset: int =0,
                        usernames : Annotated[list[str] , Query(title='Query string')] = None):
    return get_users(usernames,limit, offset, connection)


@router.post('/')
async def add_user( user: UserInDB,  connexion: cursorDep) -> dict:
    return create_user(user, connexion)

@router.get('/me', response_model=BaseUser)
async def read_user_me(user : Annotated[BaseUser, Depends(get_current_active_user)]):
    return user
