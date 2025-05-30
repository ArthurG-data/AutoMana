
from typing import Annotated,  Union, Optional, List, Any
from psycopg2 import Error
from psycopg2.extensions import connection
from fastapi import  HTTPException, APIRouter,Query, Response
from backend.database.database_utilis import create_select_query, create_delete_query, create_update_query, execute_delete_query, execute_insert_query, execute_update_query, execute_select_query, create_insert_query
from backend.modules.public.users.models import  UserPublic, UserInDB, AssignRoleRequest
from backend.database.get_database import cursorDep
from uuid import UUID

admin_user_router = APIRouter(
    prefix='/users', 
    tags=['admin-users']
)

def ensure_list(value: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    """Ensure value is always a list or None."""
    if value is None:
        return None
    return [value] if isinstance(value, str) else value

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


def patch_user(user_id: UUID, admin_id : UUID, action : str, reason:str, source_id : str, field : str, value : Any, conn: connection):
    query = create_update_query('users', [f'{field}'], ['unique_id = %s '])
    query_2 = "SELCT FROM inactivate_user(%s, %s, %s, %s, %s)"
    values = (value, str(user_id) )
    try:
        execute_update_query(conn, query,values)
        execute_insert_query(conn, query_2, (user_id, admin_id, action, reason, source_id))
        return Response(status_code=204)
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@admin_user_router.get('/', response_model=List[UserInDB], description="Return a JSON file containing the users from a list or all the users if left blank, with all info present in the DB") 
async def user_endpoints( connection : cursorDep,
                        limit : Annotated[int, Query(le=100)]=100,
                        offset: int =0,
                        usernames : Annotated[list[str] , Query(title='Query string')] = None):
    return get_users(usernames=usernames,limit=limit, offset=offset, connection=connection)


@admin_user_router.get('/{username}', response_model=UserPublic, description="get the information of a user by username") 
async def user_endpoint( connection : cursorDep,
                         username : str):
    return get_users(usernames=username, connection=connection)


@admin_user_router.delete('/{username}', description='Delete a user fom the DB')
async def delete_user(connection : cursorDep, username : str):
    try:
        return(delete_users(username, connection))
    except Exception:
        raise


@admin_user_router.post('/{user_id}/roles')
async def add_role(user_id : UUID, conn : cursorDep, role : AssignRoleRequest):
    query = """INSERT INTO user_roles (user_id, role_id)
            VALUES (%s, (
            SELECT unique_id FROM roles WHERE role = %s))
         """
    query_1 = "SET LOCAL app.current_user_id = %s"
    query_2 = "SET LOCAL app.role_change_reason = %s"
    try:
        with conn.cursor() as cur:
            cur.execute(query_1,(user_id,))
            cur.execute(query_2, (role.reason,))
            cur.execute(query,  (user_id, role.role))
        return {"status": "role added", "user_id": str(user_id), "role": role.role}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assign role: {str(e)}")    

@admin_user_router.delete('/', description="delete a list of users from the db")
async def delete_user(connection : cursorDep, username : Annotated[list[str] , Query(title='Query string')] = None):
    try:
        return(delete_users(username, connection))
    except Exception:
        raise
'''
@admin_user_router.patch('/{user_id}/promote', description='update a user to admin')
async def promote_user( admin_id : Annotated[UUID, Depends(get_current_active_user)], user_id: UUID,  conn: cursorDep):
    return(patch_user(user_id, admin_id, ,'is_admin', True, conn))
   

@admin_user_router.patch('/{user_id}/demote', description='demote an admin to user')
async def demote_admin( user_id: UUID,  conn: cursorDep):
    return(patch_user(user_id, 'is_admin', False, conn))


@admin_user_router.patch('/{user_id}/disable', description='disabled an account')
async def disable_user(user_id: UUID,  conn: cursorDep):
    return(patch_user(user_id, 'disabled', True, conn))

@admin_user_router.patch('/{user_id}/activate', description='activate an account')
async def activate_user(user_id: UUID,  conn: cursorDep):
    return(patch_user(user_id, 'disabled', False, conn))
'''