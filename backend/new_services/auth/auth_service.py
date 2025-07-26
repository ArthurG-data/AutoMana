from fastapi import HTTPException, Request,  Security
from datetime import timedelta, datetime, timezone
from fastapi.security import OAuth2PasswordBearer
from backend.dependancies import get_general_settings
from backend.new_services.auth.session_service import rotate_session_token, create_new_session
from backend.repositories.auth.auth_repository import AuthRepository
from backend.repositories.auth.session_repository import SessionRepository
from backend.schemas.user_management.user import UserInDB
from backend.modules.auth.utils import (
    verify_password, get_hash_password,
    create_access_token, decode_access_token
)
from backend.utils_new.auth.auth import verify_password, create_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

async def check_token_validity(request : Request):
    print('cheking validity')
    token = None
    auth = request.headers.get("Authorization")

    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]

    elif 'access_token' in request.cookies:
        token = request.cookies.get('access_token')
    if not token:
        raise HTTPException(status_code=401, detail='No Token')
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=400, detail="Token invalid")
  
async def get_token_from_header_or_cookie(request: Request, token: str = Security(oauth2_scheme)) -> ApiResponse:
    if token:
        return token
    cookie_token = request.cookies.get("access_token")
    return {'cookie_token': cookie_token} if cookie_token else None

def authenticate_user(repository : AuthRepository
                      , username : str
                      , password : str) -> UserInDB | None:
    user : UserInDB = repository.get_user(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

async def login(auth_repository: AuthRepository
                , session_repository :SessionRepository
                , username: str
                , password: str
                ,ip_address: str
                , user_agent: str
                ) -> dict:

    access_token_expires = timedelta(minutes=int(get_general_settings().access_token_expiry))
    expire_time = datetime.now(timezone.utc) +  timedelta(days=7)

    user = authenticate_user(auth_repository, username, password)
    session_info = await session_repository.get(user.unique_id)
    if session_info:
        await rotate_session_token(session_repository,session_info['token_id']
                                   , session_info['session_id']
                                   , session_info['refresh_token']
                                   , expire_time.isoformat())
        session_id = session_info['session_id'], refresh_token = session_info['refresh_token']
    else:
        session_id, refresh_token = await create_new_session(session_repository, user, ip_address, user_agent, expire_time)
    return {
            "session_id": str(session_id),
            "refresh_token": refresh_token,
            "access_token_expires_at": access_token_expires.isoformat(),
            "session_expires_at": expire_time.isoformat(),
           }
       
