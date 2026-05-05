import logging
from fastapi import HTTPException, Request
from datetime import timedelta, datetime, timezone
from fastapi.security import OAuth2PasswordBearer
from uuid import UUID
from automana.core.settings import get_settings as get_general_settings
from automana.api.services.auth.session_service import rotate_session_token, create_new_session
from automana.api.repositories.user_management.user_repository import UserRepository
from automana.api.repositories.auth.session_repository import SessionRepository
from automana.api.schemas.user_management.user import UserInDB
from automana.core.service_registry import ServiceRegistry
from automana.api.services.auth.auth import (verify_password, create_access_token, decode_access_token)

logger = logging.getLogger(__name__)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/auth/token")

async def check_token_validity(request : Request):
    # Accepts Bearer tokens only. Session-cookie auth for HTML/browser clients
    # is handled separately by CurrentUserDep (api/dependancies/auth/users.py);
    # this dependency guards API endpoints that expect a programmatic caller
    # supplying Authorization: Bearer <jwt>.
    logger.debug("checking_token_validity", extra={"action": "check_token_validity"})
    auth = request.headers.get("Authorization")
    settings = get_general_settings()

    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail='No Token')
    token = auth.split(" ", 1)[1]
    try:
        payload = decode_access_token(token,
                                     secret_key=settings.jwt_secret_key,
                                     algorithm=settings.jwt_algorithm)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

async def authenticate_user(repository: UserRepository,
                            username: str,
                            password: str) -> UserInDB | None:
    # Accept either username or email in the username field (email-first login UX)
    user = await repository.get(username)
    if not user:
        user = await repository.get_by_email(username)
    if not user:
        return None
    if not verify_password(password, user['hashed_password']):
        return None
    if user.get('disabled'):
        return None
    return UserInDB.model_validate(user)

@ServiceRegistry.register(
        'auth.auth.logout',
        db_repositories=['session']
)
async def logout(
        session_repository: SessionRepository,
        session_id: UUID,
        ip_address: str,
):
    await session_repository.invalidate_session(session_id, ip_address)
    # Verify the session is gone from active sessions
    row = await session_repository.get(session_id)
    if row:
        logger.warning(
            "logout_invalidation_failed",
            extra={"action": "logout", "session_id": str(session_id)},
        )
        return {"status": "error", "message": "Failed to invalidate session"}
    logger.info(
        "logout_success",
        extra={"action": "logout", "session_id": str(session_id)},
    )
    return {"status": "success", "message": "Logged out successfully"}

@ServiceRegistry.register(
        'auth.auth.login',
        db_repositories=['user', 'session']
)
async def login( user_repository: UserRepository
                , session_repository: SessionRepository  
                , username: str
                , password: str
                ,ip_address: str
                , user_agent: str
                ) -> dict:
    logger.info(
        "login_attempt",
        extra={"action": "login", "username": username, "ip_address": ip_address, "user_agent": user_agent},
    )
    # Get settings from configuration
    settings = get_general_settings()
    access_token_expires = timedelta(minutes=int(settings.access_token_expiry))
    expire_time = datetime.now(timezone.utc) + timedelta(days=7)
 
    # Authenticate user
    user = await authenticate_user(user_repository, username, password)
    if not user:
        logger.warning(
            "login_failed",
            extra={"action": "login", "username": username, "ip_address": ip_address, "user_agent": user_agent},
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Get or create session
    return_value = await session_repository.get_by_user_id(user.unique_id)
    session_info = return_value[0] if return_value else None

    if session_info:
        logger.info(
            "session_rotation",
            extra={"action": "login", "username": username, "result": "rotate_session"},
        )
        rotated = await rotate_session_token(session_repository
                                   ,session_info['session_id']
                                   ,session_info['refresh_token']
                                   ,expire_time
                                   ,session_info['token_id']
                                   )
        session_id = rotated['session_id']
        refresh_token = rotated['refresh_token']
    else:
        logger.info(
            "session_creation",
            extra={"action": "login", "username": username, "result": "create_session"},
        )
        new_session = await create_new_session(session_repository, user, ip_address, user_agent, expire_time)
        session_id = new_session["session_id"]
        refresh_token = new_session["refresh_token"]
    # Create access token
    token_data = {
        "sub": user.username,
        "user_id": str(user.unique_id),
    }
    # Create JWT token with settings from configuration
    access_token = create_access_token(
        data=token_data,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_delta=access_token_expires
    )
    return {
            "session_id": str(session_id),
            "refresh_token": refresh_token,
            "access_token": access_token,
            "access_token_expires_at": (datetime.now(timezone.utc) + access_token_expires).isoformat(),
            "session_expires_at": expire_time.isoformat(),
           }
       
