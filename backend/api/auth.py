from fastapi import APIRouter, Response, Depends, HTTPException, Request
from typing import Annotated
from backend.dependencies.general import ipDep
from fastapi.security import OAuth2PasswordRequestForm
from backend.schemas.auth.token import Token
from backend.request_handling.ApiHandler import ApiHandler

authentification_router = APIRouter(
    prefix='/auth',
    tags=['authentificate'])

@authentification_router.post('/logout'
                              , status_code=204
                              , description='remove a refresh token')
async def remove_cookie(response : Response):
    response.delete_cookie('refresh_token')

@authentification_router.post('/token'
                              , description='Using an authorization form, authentificate a user against the database and return a bearer token and a cookie with a refresh token'
                              , response_model=Token)
async def do_login(ip_address : ipDep
                   , response : Response
                   , request: Request
                   , form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) :
    #check if active session exists
    result= await ApiHandler.execute_service("auth.auth.login"
                                             , username=form_data.username
                                             , password=form_data.password
                                             , ip_address=ip_address
                                             , user_agent=request.headers.get("User-Agent"))

    if result is None:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    if "session_id" in result:
        response.set_cookie(
            key="session_id",
            value=result.data["session_id"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=60*60*24*7,
        )
    
    # Return the token
    return Token(
        access_token=result.data["access_token"],
        token_type="bearer"
    )
   

@authentification_router.post('/token/refresh', description='exanges the refresh token in a cookie for a auth token')
async def do_read_cookie(  ip_address : ipDep,response : Response, request: Request):
    return await ApiHandler.execute_service('auth.cookie.read_cookie'
                                                 , ip_address=ip_address
                                                 , response=response
                                                 , request=request)
   


