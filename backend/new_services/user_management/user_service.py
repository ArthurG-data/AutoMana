from typing import Annotated, Union
from fastapi import  Body
from backend.schemas.user_management.user import  BaseUser, UserUpdatePublic,UserInDB, UserPublic
from backend.utils_new.auth.get_hash_password import  get_hash_password
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from backend.repositories.user_management.user_repository import UserRepository
from uuid import UUID
from backend.exceptions.service_layer_exceptions.user_management import user_exceptions

async def register(user_repository: UserRepository, user : Annotated[BaseUser, Body(
    examples=[
        {
            'username' : 'johnDow',
            'email' : 'johndow@gmail.com',
            'fullname' : 'John Dow',
            'password' : 'password',
        }
    ])]) -> UserInDB:
    hashed_password = get_hash_password(user.hashed_password)
    user.hashed_password = hashed_password
 
    try:
        result = await user_repository.add(username=user.username, email=user.email, hashed_password=user.hashed_password, fullname=user.fullname)
        if not result:
            raise user_exceptions.UserCreationError("Failed to create user")
        return UserInDB.model_validate(result)
    except Exception as e:
        raise user_exceptions.UserError(f"Error creating user: {e}")

async def update(user_repository : UserRepository
                 , user_id: UUID
                 , user : UserUpdatePublic
                 ):
    """
    Update an existing user.
    """
    try:
        result = await user_repository.update(user_id, **user.model_dump())
        return UserPublic.model_validate(result)
    except Exception as e:
        raise user_exceptions.UserError(f"Error updating user: {e}")

def get_many(user_repository : UserRepository, usernames : Union[list[str], None, str], limit : int=1, offset :int=0 ) -> Union[list[UserPublic], UserPublic]:
    users = user_repository.get_users(usernames, limit, offset)
    if users:
        return PaginatedResponse(
            data=users,
            pagination_info=PaginationInfo(
                total_items=len(users),
                limit=limit,
                offset=offset
            )
        )
    else:
        return ApiResponse(
            status="error",
            message="No users found"
        )
    

async def delete_users(user_repository  : UserRepository, usernames : list[str]) :

    await user_repository.delete_users(usernames)
    return None

async def get_user(user_repository: UserRepository, username: str) -> UserInDB:
    user =  await user_repository.get(username)
    if user:
        return UserInDB(*user)
    else:
        return None

async def get_user_by_session(user_repository: UserRepository, user_id: UUID) -> UserInDB:
    try:
        user = await user_repository.get_user_from_session(user_id)
        if user:
            return UserInDB(*user)
        else:
            raise user_exceptions.UserNotFoundError("User not found")
    except Exception as e:
        raise user_exceptions.UserRepositoryError(f"Error fetching user from session: {e}")
