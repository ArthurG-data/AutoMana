import os
from fastapi import APIRouter, Response, Depends, HTTPException, status
from datetime import timedelta
from backend.models.users import BaseUser
from backend.authentification import authenticate_user, create_access_token
from typing import Annotated
from backend.dependancies import cursorDep
from fastapi.security import OAuth2PasswordRequestForm
from backend.models.utils import Token
from dotenv import load_dotenv

authentification_router = APIRouter(
    prefix='/auth',
    tags=['authentificate'])



load_dotenv()
    
@authentification_router.post('/login')
async def login(conn : cursorDep ,   response: Response, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    user = authenticate_user(conn, form_data.username, form_data.password)
  
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=int(os.getenv('ACCESS_TOKEN_EXPIRY')))
    access_token = create_access_token(
        data={"sub": user.username, "id" : str(user.unique_id)}, expires_delta=access_token_expires
    )
    refresh_token = create_access_token(
            data={"sub": user.username, "id" : str(user.unique_id)}, expires_delta=timedelta(days=7)
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=access_token_expires,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=60*60*24*7,
    )
    return Token(access_token=access_token, token_type="bearer")

