from typing import Annotated, Union
from fastapi import  Body
from backend.schemas.user_management.user import  BaseUser, UserUpdatePublic,UserInDB
from backend.utils_new.auth import  get_hash_password
from backend.request_handling.StandardisedQueryResponse import ApiResponse, PaginatedResponse, PaginationInfo
from backend.repositories.user_management.user_repository import UserRepository
from uuid import UUID
from backend.exceptions import user_exceptions

async def add(repository: UserRepository, user : Annotated[BaseUser, Body(
    examples=[
        {
            'username' : 'johnDow',
            'email' : 'johndow@gmail.com',
            'fullname' : 'John Dow',
            'password' : 'password',
        }
    ])]) -> dict:
    hashed_password = get_hash_password(user.hashed_password)
    user.hashed_password = hashed_password
    values = (user.username, user.email, user.fullname, user.hashed_password)
    try:
        await repository.add(values)
        return ApiResponse(
            status="success",
            message="User added successfully"
        )
    except Exception as e:
        return ApiResponse(
            status="error",
            message="error adding a new user"
        )

async def update(repository : UserRepository, username : str, user : UserUpdatePublic) -> ApiResponse:
    """
    Update an existing user.
    """
    try:
        await repository.update(username, user)
        return ApiResponse(
            status="success",
            message="User updated successfully"
        )
    except Exception as e:
        return ApiResponse(
            status="error",
            message="error updating user"
        )


def get_many(repository : UserRepository, usernames : Union[list[str], None, str], limit : int=1, offset :int=0 ) -> Union[list[UserPublic], UserPublic]:
    users = repository.get_users(usernames, limit, offset)
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
    

async def delete_users(repository : UserRepository, usernames : list[str]) :
    
    await repository.delete_users(usernames)
    return None      
      
def update_user(repository: UserRepository):
    raise NotImplementedError("Update user functionality is not implemented yet.")

async def get_user(repository: UserRepository, username: str) -> UserInDB:
    user =  await repository.get(username)
    if user:
        return UserInDB(*user)
    else:
        return None

async def get_user_by_session(repository: UserRepository, user_id: UUID) -> UserInDB:
    try:
        user = await repository.get_user_from_session(user_id)
        if user:
            return UserInDB(*user)
        else:
            raise user_exceptions.UserNotFoundError("User not found")
    except Exception as e:
        raise user_exceptions.UserRepositoryError(f"Error fetching user from session: {e}")
