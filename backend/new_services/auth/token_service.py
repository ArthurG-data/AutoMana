from backend.schemas.auth.cookie import CookiesData
from backend.schemas.auth.token import Token
from backend.utils.auth.cookie_utils import extract_session_id
from backend.utils.auth import auth
from backend.repositories.auth.session_repository import SessionRepository
from uuid import UUID
from datetime import datetime, timedelta, timezone
from backend.core.settings import get_settings as get_general_settings

async def validate_session_from_cookie(repository: SessionRepository, cookies: CookiesData):
    session_id = extract_session_id(cookies)
    ip_address = cookies.ip_address
    user_agent = cookies.user_agent
    return await repository.get(session_id, ip_address, user_agent)#maybe chnage this to get the session_id from the cookies and check if it exists in the db

async def get_user_from_cookie(repository: SessionRepository, cookies: CookiesData):
    session_id = extract_session_id(cookies)
    if not session_id:
        return None
    session = await repository.get(session_id=session_id, ip_address=cookies.ip_address, user_agent=cookies.user_agent)
    if not session:
        return None
    return session.user

async def refresh_tokens(repository
                         , token_repository
                        , token_id
                        , session_id
                        , refresh_token
                        , refresh_expiry
                        , user : dict):
    refresh_token = await repository.rotate_refresh_token(
        token_id=token_id,
        session_id=session_id,
        refresh_token=refresh_token,
        refresh_expiry=refresh_expiry
    )
    access_token_expires = timedelta(minutes=int(get_general_settings().access_token_expiry))
    access_token = auth.create_access_token( data={"sub": user.username, "id" : str(user.unique_id), "role":user.role},expires_delta=access_token_expires)
    refresh_expiry = now_utc() + timedelta(days=7)
    refresh_token = auth.create_access_token(
            data={"sub": user.username, "id" : str(user.unique_id), "role":user.role}, expires_delta=timedelta(days=7)
        )
    new_token_id = await  token_repository.rotate_token(
        token_id,
        session_id,
        refresh_token,
        refresh_expiry
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "token_id": str(new_token_id),
        "refresh_token": refresh_token,
        "access_token_expires_at": (datetime.now(timezone.utc) + access_token_expires).isoformat(),
        "refresh_token_expires_at": refresh_expiry.isoformat()
    }

async def refresh_tokens(repository
                        , token_id
                        , session_id
                        , refresh_token
                        , refresh_expiry):
    await repository.rotate_refresh_token(
        token_id=token_id,
        session_id=session_id,
        refresh_token=refresh_token,
        refresh_expiry=refresh_expiry
    )

async def process_token_refresh(
    session_repository: SessionRepository,
    token_repository: TokenRepository,
    user_repository: UserRepository,
    cookies: CookiesData
) -> dict:
   
    # Validate session
    session_data = await validate_session_from_cookie(session_repository, cookies)
    
    # Get refresh token
    refresh_token = session_data.get("refresh_token")
    if not refresh_token:
        return None
    # Get user from token
    user_data = await get_user_from_cookie(
        token_repository,
        user_repository,
        refresh_token
    )
    
    # Generate new tokens
    token_result = await refresh_tokens(
        token_repository,
        session_data["session_id"],
        session_data["token_id"],
        user_data
    )
    
    return Token(access_token=access_token, token_type="bearer")