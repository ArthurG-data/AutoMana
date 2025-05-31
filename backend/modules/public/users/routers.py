from fastapi import APIRouter, Depends
from backend.modules.auth.models import  BaseUser, UserPublic
from backend.modules.public.users.models import   UserUpdatePublic

from backend.modules.auth.dependancies   import  currentActiveUser
from backend.shared.dependancies import currentActiveSession
from backend.database.get_database import cursorDep
from backend.modules.public.users.services import create_user, update_user

router = APIRouter(
    tags=['users'],
    responses={404:{'description' : 'Not found'}}
)

@router.get('/me', response_model= UserPublic)
async def get_me_user(current_user: currentActiveUser):
    return current_user

@router.post('/')
async def add_user( user: BaseUser,  connexion: cursorDep) -> dict:
    return create_user(user, connexion)

@router.put('/')
async def modify_user( user_update: UserUpdatePublic, connection : cursorDep, current_user :currentActiveUser):
    return update_user(current_user.username, user_update, connection)

@router.get('/session')
async def get_session(session : currentActiveSession):
    return {'session' : session}