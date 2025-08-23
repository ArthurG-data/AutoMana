from fastapi import APIRouter, Response, Depends, HTTPException, Request
from typing import Annotated

from fastapi.responses import JSONResponse
from backend.dependancies.general import ipDep
from fastapi.security import OAuth2PasswordRequestForm
from backend.schemas.auth.token import Token, TokenResponse
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.service_deps import get_service_manager
import logging

logger = logging.getLogger(__name__)

authentification_router = APIRouter(
    prefix='/auth',
    tags=['authentificate'])

@authentification_router.post('/logout'
                              , status_code=204
                              , description='remove a refresh token')
async def logout(ip_address : ipDep
                ,response : Response
                 ,request : Request
                 ,service_manager: ServiceManager = Depends(get_service_manager)
                 ):
    session_id = request.cookies.get("session_id")
    if session_id:
        returned = await service_manager.execute_service('auth.auth.logout'
                                                         , session_id=session_id
                                                         , ip_address=ip_address)
        if returned.get("status") == "error":
            logger.warning(f"Logout failed for session {session_id}: {returned.get('message')}")
    response.delete_cookie('session_id')
    return None

@authentification_router.post('/token'
                              , description='Using an authorization form, authentificate a user against the database and return a bearer token and a cookie with a refresh token'
                              , response_model=TokenResponse)
async def do_login(ip_address : ipDep
                   , request: Request
                   , form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
                   , service_manager: ServiceManager = Depends(get_service_manager)
                   ) :
    #check if active session exists
    result = await service_manager.execute_service("auth.auth.login"
                                             , username=form_data.username
                                             , password=form_data.password
                                             , ip_address=ip_address
                                             , user_agent=request.headers.get("User-Agent"))
    if result is None:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    
    # Return the token
    token_response = TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        token_type="bearer",
        expires_in=3600
    )
    json_response = JSONResponse(
            content=token_response.model_dump(),
            status_code=200
        )
    
    if "session_id" in result:
        json_response.set_cookie(
            key="session_id",
            value=result["session_id"],
            httponly=False,
            secure=False,
            samesite="strict",
            max_age=60*60*24*7,
        )
    json_response.set_cookie(
            key="access_token",
            value=result["access_token"],
            httponly=False,
            secure=False,
            samesite="strict",
            max_age=3600,  # 1 hour
        )
    return json_response
   
@authentification_router.post('/token/refresh', description='exanges the refresh token in a cookie for a auth token')
async def do_read_cookie(ip_address: ipDep, 
                        response: Response, 
                        request: Request,
                        service_manager: ServiceManager = Depends(get_service_manager)):
    return await service_manager.execute_service('auth.cookie.read_cookie'
                                                 , ip_address=ip_address
                                                 , response=response
                                                 , request=request)
   


