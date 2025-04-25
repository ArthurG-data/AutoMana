import os
from fastapi import APIRouter, Response, Depends, HTTPException, status, Request
from datetime import timedelta
from backend.authentification import authenticate_user, create_access_token, decode_access_token, get_token_from_header_or_cookie, get_current_user
from typing import Annotated
from backend.dependancies import cursorDep
from fastapi.security import OAuth2PasswordRequestForm
from backend.models.utils import Token
from backend.models.users import CreateSession, UserInDB

authentification_router = APIRouter(
    prefix='/auth',
    tags=['authentificate'])


@authentification_router.post('/token', description='Using an authorization form, authentificate a user against the database and return a bearer token and a cookie with a refresh token')
async def login(conn : cursorDep ,   response : Response, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    user = authenticate_user(conn, form_data.username, form_data.password)
  
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=int(os.getenv('ACCESS_TOKEN_EXPIRY')))
    access_token = create_access_token(
        data={"sub": user.username, "id" : str(user.unique_id), "role":user.role},expires_delta=access_token_expires
    )
    refresh_token = create_access_token(
            data={"sub": user.username, "id" : str(user.unique_id), "role":user.role}, expires_delta=timedelta(days=7)
    )


    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=60*60*24*7,
    )
    return Token(access_token=access_token, token_type="bearer")



def extract_ip (request : Request)-> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0]  # Use the first IP
    else:
        ip = request.client.host
    return ip


@authentification_router.post('/session', description='create a session for a user, add an entry to the DB')
async def add_session(  conn : cursorDep, request: Request, token : str = Depends(get_token_from_header_or_cookie)):
    decoded_token = decode_access_token(token)
    ip = extract_ip(request)
    id = decoded_token.get('id')
    new_session = CreateSession(id, ip_address=ip,)
    return new_session

@authentification_router.get('/exange-cookie', description='exanges the refresh token in a cookie for a auth token')
async def read_cookie( conn : cursorDep,request: Request):
    cookie = request.cookies.get('refresh_token')
    user : UserInDB =  await get_current_user(conn, token=cookie)
    if not user.disabled:
        access_token_expires = timedelta(minutes=int(os.getenv('ACCESS_TOKEN_EXPIRY')))
        access_token = create_access_token( data={"sub": user.username, "id" : str(user.unique_id), "role":user.role},expires_delta=access_token_expires)
        return Token(access_token=access_token, token_type="bearer")
   
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token Invalid",
        headers={"WWW-Authenticate": "Bearer"},
    )

@authentification_router.post('/logout', status_code=204, description='remove a refresh token')
async def remove_cookie(response : Response):
    response.delete_cookie('refresh_token')
    