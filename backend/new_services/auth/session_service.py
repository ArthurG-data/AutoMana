from backend.repositories.auth.session_repository import SessionRepository
from uuid import UUID, uuid4
from backend.schemas.auth.session import CreateSession
from backend.utils_new.auth.auth import create_access_token, decode_access_token
from backend.request_handling.StandardisedQueryResponse import ApiResponse
from datetime import timedelta, datetime
from backend.exceptions import session_exceptions
from backend.schemas.user_management.user import UserInDB
from backend.dependancies.settings import get_general_settings
import logging 
logger = logging.getLogger(__name__)

async def get_session(repository :SessionRepository,
    session_id: UUID):
    """
    Fetches a session by its ID.
    
    Args:
        repository (SessionRepository): The session repository instance.
        session_id (UUID): The unique identifier of the session.
    
    Returns:
        dict: The session data if found, otherwise None.
    """
    return await repository.get(session_id)

async def delete_session(repository: SessionRepository, ip_address: str, user_id: UUID, session_id: UUID):
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
    return await repository.delete(ip_address, user_id, session_id)

async def update_session(repository: SessionRepository, session_id: UUID, data: dict):
    """
    Updates a session with the provided data.
    
    Args:
        repository (SessionRepository): The session repository instance.
        session_id (UUID): The unique identifier of the session to update.
        data (dict): The data to update the session with.
    
    Returns:
        bool: True if the session was updated successfully, otherwise False.
    """
    return await repository.update(session_id, data)

async def insert_session(repository: SessionRepository, new_session : CreateSession):
    """"Inserts a new session into the database."""
    values = (new_session.session_id, str(new_session.user_id), new_session.created_at, new_session.expires_at, new_session.ip_address, new_session.user_agent, new_session.refresh_token, new_session.refresh_token_expires_at, new_session.device_id,)
    await repository.add(values)
    result = await repository.get(new_session.session_id)
    if result:
        print(f"Session inserted successfully: {result}")
        raw_result = result[0]
        return raw_result['session_id'], raw_result['refresh_token']
    else:
        logger.error(f"Failed to insert session: {new_session.session_id}")
        return None

async def get_active_session(repository: SessionRepository, user_id: UUID):
    result = await repository.get(user_id)
    if result:
        return ApiResponse(
            status="success",
            data=result
        )
    else:
        return ApiResponse(
            status="error",
            message="No active session found for the user."
        )

async def rotate_session_token(repository: SessionRepository
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
        await repository.rotate_token(token_id
                                      ,session_id
                                      ,refresh_token
                                      ,expire_time)
        return {'session_id': session_id, 'refresh_token': refresh_token}

async def create_new_session(repository: SessionRepository, user: UserInDB, ip_address: str, user_agent: str, expire_time: str):
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
    session_id, _ = await insert_session(repository, new_session)
    return {'session_id': session_id, 'refresh_token': refresh_token}

async def validate_session_credentials(repository: SessionRepository, session_id: UUID, ip_address: str, user_agent: str) -> ApiResponse:
    result = await repository.validate_session_credentials(session_id, ip_address, user_agent)
    return ApiResponse(
        status="success",
        data=result
    ) if result else ApiResponse(
        status="error",
        message="Invalid session credentials")

async def validate_token_and_get_session_id(
        repository: SessionRepository
        ,token: str)->UUID:
    try:
        payload = decode_access_token(token)
        if not payload:
            raise session_exceptions.InvalidTokenError("Invalid token")
        
        session_id = payload.get('session_id')
        if not session_id:
            raise session_exceptions.InvalidTokenError("Session ID not found in token")
        
        session = await repository.get(UUID(session_id))
        if not session:
            raise session_exceptions.SessionNotFoundError(f"Session with ID {session_id} not found")
        return UUID(session_id)
    except Exception as e:
        raise session_exceptions.InvalidTokenError("Failed to validate token")






