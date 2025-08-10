from fastapi import Depends, HTTPException, Request, Cookie, status
from typing import Annotated, Optional
from backend.request_handling.QueryExecutor import QueryExecutor, AsyncQueryExecutor
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.general import get_service_manager
from backend.schemas.user_management.user import UserInDB, UserPublic
from backend.dependancies.general import ipDep

async def get_query_executor() -> QueryExecutor:
    from backend.main import query_executor
    """Get the global query executor instance from the application state"""
    # Return the global query_executor that was initialized in the lifespan context manager
    # This ensures we use the same connection pool throughout the application
    return query_executor

async def get_service_manager() -> ServiceManager:
    """Get the ServiceManager instance from global application state"""
    from backend.main import service_manager
    if service_manager is None:
        raise RuntimeError("ServiceManager not initialized")
    return service_manager


async def get_current_active_user(
    ip_address: ipDep,
    request: Request,
    session_id: Optional[str] = Cookie(None),
    service_manager: ServiceManager = Depends(get_service_manager)
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
