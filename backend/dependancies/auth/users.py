from backend.schemas.user_management.user import UserInDB
from fastapi import  Depends
from typing import Annotated
from backend.dependancies.general import ipDep
from fastapi import Request, Cookie, HTTPException, status
from typing import Optional
from backend.dependancies.service_deps import ServiceManagerDep

async def get_current_active_user(
    ip_address: ipDep,
    request: Request,
    service_manager: ServiceManagerDep,
    session_id: Optional[str] = Cookie(None),
) -> UserInDB:
    """
    Dependency that extracts the session ID cookie and returns the active user.
    
    This uses the service manager to validate the session and get user details.
    """
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_agent = request.headers.get("User-Agent")
    # Get user information from the session
    user = await service_manager.execute_service(
        "auth.session.get_user_from_session",
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if not user:
        # Clear invalid cookie
        response = request.scope.get("response")
        if response:
            response.delete_cookie("session_id")
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Convert to UserInDB model
    return UserInDB(**user)

# Type alias for authenticated user dependency
CurrentUserDep = Annotated[UserInDB, Depends(get_current_active_user)]
