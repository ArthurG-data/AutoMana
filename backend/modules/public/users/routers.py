from fastapi import APIRouter

from fastapi import APIRouter, Depends
from backend.modules.public.users.models import  BaseUser, UserPublic,  UserUpdatePublic
from backend.shared.dependancies  import  currentActiveUser, currentActiveSession
from backend.database.get_database import cursorDep
from backend.modules.public.users import services

router = APIRouter(
    tags=['users'],
    responses={404:{'description' : 'Not found'}}
)

@router.get('/me', response_model= UserPublic)
async def get_me_user(current_user: currentActiveUser):
    return current_user

@router.post('/')
async def add_user( user: BaseUser,  connexion: cursorDep) -> dict:
    return services.create_user(user, connexion)

@router.put('/')
async def modify_user( user_update: UserUpdatePublic, connection : cursorDep, current_user :currentActiveUser):
    return services.update_user(current_user.username, user_update, connection)

@router.get('/session')
async def get_session(session : currentActiveSession):
    return {'session' : session}