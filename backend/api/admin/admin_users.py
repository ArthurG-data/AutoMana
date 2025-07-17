
from typing import Annotated, List
from fastapi import  HTTPException, APIRouter,Query
from backend.modules.public.users.models import  UserPublic, AssignRoleRequest
from backend.modules.auth.models import UserInDB
from backend.database.get_database import cursorDep
from backend.modules.admin.admin_users_services import get_users, delete_users, add_role as add_role_service
from uuid import UUID

admin_user_router = APIRouter(
    prefix='/users', 
    tags=['admin-users']
)


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
async def assign_role(user_id : UUID, role : AssignRoleRequest, conn : cursorDep):
    """
    Assign a role to a user.
    """
    await add_role_service(user_id, conn, role)
   
@admin_user_router.delete('/', description="delete a list of users from the db")
async def delete_user(connection : cursorDep, username : Annotated[list[str] , Query(title='Query string')] = None):
    try:
        return(delete_users(username, connection))
    except Exception:
        raise