from typing import Annotated, Union, Optional
from fastapi import  Body
from backend.schemas.user_management.user import  BaseUser, UserUpdatePublic,UserInDB, UserPublic
from backend.utils.auth.get_hash_password import  get_hash_password
from backend.repositories.user_management.user_repository import UserRepository
from uuid import UUID
from backend.exceptions.service_layer_exceptions.user_management import user_exceptions
import logging

logger = logging.getLogger(__name__)

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

async def search_users(user_repository : UserRepository,
    # Search parameters
    username: Optional[str] = None,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    search_query: Optional[str] = None,
    user_id: Optional[UUID] = None,
    # Filters
    disabled: Optional[bool] = None,
    #role: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    # Pagination
    limit: int = 20,
    offset: int = 0,
    # Sorting
    sort_by: str = "username",
    sort_order: str = "asc",) -> Union[list[UserPublic], UserPublic]:
    print(f"Searching users with parameters: {locals()}")
    try:
        # If searching for specific user ID, use get method
        if user_id:
            print("Fetching user by ID")
            user = await user_repository.get_by_id(user_id)
            if not user:
                return {"users": [], "total_count": 0}
            
            # Convert to appropriate model based on permission level
          
           
            user_data = UserInDB.model_validate(user)
                
            return {
                "users": [user_data.model_dump()],
                "total_count": 1
            }
        result = await user_repository.search_users(
            username=username,
            email=email,  # Only admin can search by email
            full_name=full_name,
            search_query=search_query,
            disabled=disabled,
           # role=role,  # Only admin can filter by role
            created_after=created_after,
            created_before=created_before,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        users = result.get("users", [])
        total_count = result.get("total_count", 0)
        return {
            "users": users,
            "total_count": total_count
        }
        
    except Exception as e:
        logger.error(f"Error searching users: {str(e)}")
        raise user_exceptions.UserSearchError(f"Search failed: {str(e)}")
    
    

async def delete_user(user_repository  : UserRepository, user_id : UUID) :

    await user_repository.delete(user_id)
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
