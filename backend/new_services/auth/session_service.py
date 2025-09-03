from backend.repositories.auth.session_repository import SessionRepository
from uuid import UUID, uuid4
from backend.schemas.auth.session import CreateSession
from backend.utils_new.auth.auth import create_access_token, decode_access_token
from backend.request_handling.StandardisedQueryResponse import ApiResponse
from datetime import timedelta, datetime, timezone
from backend.exceptions import session_exceptions
from backend.schemas.user_management.user import UserInDB
from backend.dependancies.settings import get_general_settings
import logging 
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def validate_session_credentials(
        repository: SessionRepository,
        session_id: UUID
        , ip_address: str
        , user_agent: str) -> dict:
    """
    Fetches a session by its ID.
    
    Args:
        repository (SessionRepository): The session repository instance.
        session_id (UUID): The unique identifier of the session.
    
    Returns:
        dict: The session data if found, otherwise None.
    """
    # Get session from repository
    try:
        session = await repository.validate_session_credentials(session_id, ip_address, user_agent)
        session = session[0] if session else None
    
    except Exception as e:
        logger.error(f"Error fetching session: {str(e)}")
        raise session_exceptions.SessionError("Failed to fetch session")
    # Check if session is expired
    session_expires_at = session.get("session_expires_at")
    if session_expires_at < datetime.now(timezone.utc):
        raise session_exceptions.SessionExpiredError(f"Session {session_id} is expired")
    return session

async def get_user_from_session(
    session_repository,
    user_repository,
    session_id: str,
    ip_address: str,
    user_agent: str
) -> Dict[str, Any]:
    """Get user information from a session ID"""
    try:
        # First validate the session
        session = await validate_session_credentials(session_repository, session_id, ip_address, user_agent)
        # Get the user ID from the session
        user_id = session.get("user_id")
        
        if not user_id:
            logger.warning(f"Session {session_id} has no user_id")
            raise session_exceptions.SessionUserNotFoundError( "Session has no user_id")

        # Get the user from the repository
        user = await user_repository.get_by_id(user_id)
        
        if not user:
            logger.warning(f"User not found for session {session_id}")
            raise session_exceptions.UserSessionNotFoundError("Session has no user_id")
        return user
    except session_exceptions.SessionError:
        raise
    except Exception as e:
        logger.error(f"Error getting user from session: {str(e)}")
        raise session_exceptions.SessionNotFoundError("Failed to get user from session")

async def delete_session(session_repository: SessionRepository
                         , ip_address: str
                         , user_id: UUID,
                           session_id: UUID):
    """
    Deletes a session by its ID.
    
    Args:
        repository (SessionRepository): The session repository instance.
        ip_address (str): The IP address of the user.
        user_id (UUID): The unique identifier of the user.
        session_id (UUID): The unique identifier of the session to delete.
    
    Returns:
        bool: True if the session was deleted successfully, otherwise False.
    """
    await session_repository.delete(ip_address, user_id, session_id)

async def update_session(session_repository: SessionRepository, session_id: UUID, data: dict):
    """
    Updates a session with the provided data.
    
    Args:
        repository (SessionRepository): The session repository instance.
        session_id (UUID): The unique identifier of the session to update.
        data (dict): The data to update the session with.
    
    Returns:
        bool: True if the session was updated successfully, otherwise False.
    """
    return await session_repository.update(session_id, data)

async def insert_session(session_repository: SessionRepository, new_session : CreateSession):
    """"Inserts a new session into the database."""
    values = (new_session.session_id, str(new_session.user_id), new_session.created_at, new_session.expires_at, new_session.ip_address, new_session.user_agent, new_session.refresh_token, new_session.refresh_token_expires_at, new_session.device_id,)
    await session_repository.add(values)
    result = await session_repository.get(new_session.session_id)
    if result:
        print(f"Session inserted successfully: {result}")
        raw_result = result[0]
        return raw_result['session_id'], raw_result['refresh_token']
    else:
        logger.error(f"Failed to insert session: {new_session.session_id}")
        return None


async def rotate_session_token(session_repository: SessionRepository
                               , session_id: UUID
                               , refresh_token: str
                               , expire_time: datetime
                               , token_id: UUID):
        settings = get_general_settings()
        refresh_token = create_access_token(data={"session_id": str(session_id)}
                                            , expires_delta=timedelta(days=7)
                                            , secret_key=settings.secret_key
                                            , algorithm=settings.encrypt_algorithm
                                            )
        await session_repository.rotate_token(token_id
                                      ,session_id
                                      ,refresh_token
                                      ,expire_time)
        return {'session_id': session_id, 'refresh_token': refresh_token}

async def create_new_session(session_repository: SessionRepository, user: UserInDB, ip_address: str, user_agent: str, expire_time: str):
    session_id = uuid4()
    settings = get_general_settings()
    logger.info(f"Creating new session for user {user.username} with ID {session_id} at IP {ip_address} and user agent {user_agent}")
    refresh_token = create_access_token(data={"session_id": str(session_id)}, secret_key=settings.secret_key, algorithm=settings.encrypt_algorithm, expires_delta=timedelta(days=7))
    new_session = CreateSession(
        session_id=session_id,
        user_id=user.unique_id,
        ip_address=ip_address,
        refresh_token=refresh_token,
        refresh_token_expires_at=expire_time,
        user_agent=user_agent
    )
    session_id, _ = await insert_session(session_repository, new_session)
    return {'session_id': session_id, 'refresh_token': refresh_token}


async def validate_token_and_get_session_id(
        session_repository: SessionRepository
        ,token: str)->UUID:
    try:
        payload = decode_access_token(token)
        if not payload:
            raise session_exceptions.InvalidTokenError("Invalid token")
        
        session_id = payload.get('session_id')
        if not session_id:
            raise session_exceptions.InvalidTokenError("Session ID not found in token")

        session = await session_repository.get(UUID(session_id))
        if not session:
            raise session_exceptions.SessionNotFoundError(f"Session with ID {session_id} not found")
        return UUID(session_id)
    except Exception as e:
        raise session_exceptions.InvalidTokenError("Failed to validate token")


async def read_session(session_repository: SessionRepository, session_id: UUID):
    """Reads a session from the database."""
    session = await session_repository.get(session_id)
    if not session:
        logger.error(f"Session not found: {session_id}")
        return None
    return session
