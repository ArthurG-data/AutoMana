import logging
from fastapi import HTTPException, Request,  Security
from datetime import timedelta, datetime, timezone
from fastapi.security import OAuth2PasswordBearer
from uuid import UUID
from backend.core.settings import Settings,  get_settings as get_general_settings
from backend.new_services.auth.session_service import rotate_session_token, create_new_session
from backend.repositories.auth.auth_repository import AuthRepository
from backend.repositories.user_management.user_repository import UserRepository
from backend.repositories.auth.session_repository import SessionRepository
from backend.schemas.user_management.user import UserInDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from backend.utils.auth.auth import (verify_password
                                         ,create_access_token
                                         ,decode_access_token)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

async def check_token_validity(request : Request):
    print('checking validity')
    token = None
    auth = request.headers.get("Authorization")
    settings = get_general_settings()

    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]

    elif 'access_token' in request.cookies:
        token = request.cookies.get('access_token')
    if not token:
        raise HTTPException(status_code=401, detail='No Token')
    try:
        payload = decode_access_token(token, 
                                     secret_key=settings.jwt_secret_key,
                                     algorithm=settings.jwt_algorithm)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
  
async def get_token_from_header_or_cookie(request: Request, token: str = Security(oauth2_scheme)) -> dict:
    if token:
        return token
    cookie_token = request.cookies.get("access_token")
    return {'cookie_token': cookie_token} if cookie_token else None

async def authenticate_user(repository : UserRepository
                      , username : str
                      , password : str) -> UserInDB | None:
    user  = await repository.get(username)
    if not user:
        return None
    if not verify_password(password, user['hashed_password']):
        return None
    return UserInDB.model_validate(user)

async def logout(
        session_repository: SessionRepository,
        session_id: UUID,
        ip_address: str,
):
    #check that the user is matches the user in the session
    if session_id:
        # Invalidate the session in the database
        await session_repository.invalidate_session(session_id, ip_address)
        logger.info(f"Session {session_id} invalidated during logout")
    #check the session status
    row = await session_repository.get(session_id)
    if not row:
        logger.warning(f"Session {session_id} not found during logout")
        return {"status": "error", "message": "Session not found"}
    return {"status": "success", "message": "Logged out successfully"}

async def login( user_repository: UserRepository
                , session_repository: SessionRepository  
                , username: str
                , password: str
                ,ip_address: str
                , user_agent: str
                ) -> dict:
    logger.info(f"User {username} is attempting to log in from IP {ip_address} with user agent {user_agent}")#modify apihandler later, or merge both repo
    # Get settings from configuration
    settings = get_general_settings
    access_token_expires = timedelta(minutes=int(settings.access_token_expiry))
    expire_time = datetime.now(timezone.utc) + timedelta(days=7)
 
    # Authenticate user
    user = await authenticate_user(user_repository, username, password)
    if not user:
        logger.warning(f"User {username} failed to log in from IP {ip_address} with user agent {user_agent}")
        return {"error": "Invalid username or password"}
    
    # Get or create session
    return_value = await session_repository.get_by_user_id(user.unique_id)
    session_info = return_value[0] if return_value else None

    if session_info:
        logger.info(f"User {username} has an existing session, rotating session token")
        await rotate_session_token(session_repository
                                   ,session_info['session_id']
                                   ,session_info['refresh_token']
                                   ,expire_time
                                   ,session_info['token_id']
                                   )
        session_id = session_info['session_id']
        refresh_token = session_info['refresh_token']
    else:
        logger.info(f"User {username} has no existing session, creating a new session")
        session_id, refresh_token = await create_new_session(session_repository, user, ip_address, user_agent, expire_time)
    # Create access token
    token_data = {
        "sub": user.username,
        "user_id": str(user.unique_id),
    }
    # Create JWT token with settings from configuration
    access_token = create_access_token(
        data=token_data,
        secret_key=settings.secret_key,
        algorithm=settings.encrypt_algorithm,
        expires_delta=access_token_expires
    )
    return {
            "session_id": str(session_id),
            "refresh_token": refresh_token,
            "access_token": access_token,
            "access_token_expires_at": (datetime.now(timezone.utc) + access_token_expires).isoformat(),
            "session_expires_at": expire_time.isoformat(),
           }
       
