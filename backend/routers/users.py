

from typing import Annotated,  Union, Optional, List
from psycopg2 import Error
from psycopg2.extensions import connection
from fastapi import  Body, HTTPException, APIRouter, Depends,  Query, Response
from backend.database.database_utilis import create_insert_query, create_select_query, create_delete_query, create_update_query, execute_delete_query, execute_insert_query,execute_update_query, execute_select_query, delete_rows
from backend.models.users import  BaseUser, UserPublic,  UserUpdate, Session
from backend.authentification import get_current_user, get_hash_password, get_current_active_user, check_token_validity
from backend.dependancies import cursorDep


router = APIRouter(
    prefix='/users',
    tags=['users'],
    dependencies=[Depends(check_token_validity)],
    responses={404:{'description' : 'Not found'}}
)


def ensure_list(value: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    """Ensure value is always a list or None."""
    if value is None:
        return None
    return [value] if isinstance(value, str) else value


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
    query = create_insert_query('users', ['username', 'email','fullname', 'hashed_password'])
    
    values = (user.username, user.email, user.fullname, user.hashed_password)
    try:
        ids = execute_insert_query(connexion,query, values)
        return {'message' : 'user added successfuly', 'ids' : ids}
    except Exception as e:
        raise
     

   
def get_users(usernames : Union[list[str], None, str],connection : connection, limit : int=1, offset :int=0 ) -> Union[list[UserPublic], UserPublic]:
    select_many = False
    if isinstance(usernames, list):    
        condition_lists = ['username = Any(%s)' ]
        select_many = True
    else:
        condition_lists = ['username = %s']

    values =  (usernames , limit, offset)
    
    if usernames is None:
        condition_lists = []
        values =  (limit, offset)
        select_many=True
     
    query = create_select_query('users', conditions_list=condition_lists)

    try:
        users = execute_select_query(connection, query, values,select_all=select_many)
        if not users:
            raise HTTPException(status_code=404, detail='Users not found')
       
        return users
    except HTTPException as e:
        raise e 

    except Error as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {db_err}") 

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

def delete_users(usernames : Union[list[str], str], connection : connection) :
    usernames = ensure_list(usernames)
    query = create_delete_query('users', ['username = ANY(%s)'])

    try:
        execute_delete_query(connection, query, (usernames,), execute_many=False)
        return Response(status_code=204)
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# need to be completed
def update_user(username : str, user : Annotated[UserUpdate, Body(
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
    """ UPDATE users SET username = %s, email = %s, fullname = %s, hashed_password = %s; """



\
@router.get('/', response_model=List[UserPublic]) 
async def user_endpoints( connection : cursorDep,
                        limit : Annotated[int, Query(le=100)]=100,
                        offset: int =0,
                        usernames : Annotated[list[str] , Query(title='Query string')] = None):
    return get_users(usernames=usernames,limit=limit, offset=offset, connection=connection)

@router.get('/test')
async def test():
    return {'status' : 'ok'}


@router.get('/{username}', response_model=UserPublic) 
async def user_endpoint( connection : cursorDep,
                         username : str):
    return get_users(usernames=username, connection=connection)

@router.get('/me', response_model=BaseUser)
async def read_user_me(user : Annotated[BaseUser, Depends(get_current_active_user)]):
    return user


@router.delete('/{username}')
async def delete_user(connection : cursorDep, username : str):
    try:
        return(delete_users(username, connection))
    except Exception:
        raise

@router.delete('/')
async def delete_user(connection : cursorDep, username : Annotated[list[str] , Query(title='Query string')] = None):
    try:
        return(delete_users(username, connection))
    except Exception:
        raise

@router.post('/')
async def add_user( user: BaseUser,  connexion: cursorDep) -> dict:
    return create_user(user, connexion)

@router.put('/{username}')
async def modify_user(username : str, user_update: UserUpdate, connection : cursorDep):
    update_user(username, user_update, connection)

@router.post('/session')
async def create_session(session : Session, connection : cursorDep):
    return session

@router.get('/refresh')
async def refresh_access_token():
    pass

@router.get('/logout')
async def logout_user():
    pass


@router.get('/test')
async def test():
    return {'status' : 'ok'}
