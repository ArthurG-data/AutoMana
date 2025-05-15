
from fastapi import APIRouter, Response, Depends, HTTPException, Request
from typing import Annotated
from backend.dependancies import ipDep
from backend.database.get_database import cursorDep
from fastapi.security import OAuth2PasswordRequestForm
from backend.routers.auth.models import Token
from backend.routers.auth.services import login, read_cookie

authentification_router = APIRouter(
    tags=['authentificate'])

@authentification_router.post('/token', description='Using an authorization form, authentificate a user against the database and return a bearer token and a cookie with a refresh token', response_model=Token)
async def do_login(conn : cursorDep ,  ip_address : ipDep, response : Response, request: Request, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) :
    try:
        return await login(conn, ip_address, response,request,form_data)
    except Exception as e:
        return HTTPException(status_code=400, detail='Authentification failed')
    
@authentification_router.post('/exange-cookie', description='exanges the refresh token in a cookie for a auth token')
async def do_read_cookie( conn : cursorDep, ip_address : ipDep,response : Response, request: Request):
    try:
        return await read_cookie(conn, ip_address,response, request )
    except Exception as e:
        return HTTPException(status_code=401, detail='Could not exange cookie')

@authentification_router.post('/logout', status_code=204, description='remove a refresh token')
async def remove_cookie(response : Response):
    response.delete_cookie('refresh_token')
    
