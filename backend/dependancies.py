from fastapi import Header, HTTPException, Depends, Request
from typing_extensions import Annotated, Optional
from pydantic import Field
from backend.database.get_database import connection, get_connection
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    postgres_host : str
    postgres_password : str
    postgres_db : str
    postgres_user : str

    secret_key : str
    encrypt_algorithm : str
    access_token_expiry : int =Field(title='The duration in minute of the access token', default=30)

    ebay_client_id : str
    ebay_redirect_uri : str
    ebay_client_secret : str
    model_config =  SettingsConfigDict(env_file='.env')

@lru_cache
def get_settings():
    return Settings()


async def get_token_header(x_token: Annotated[str, Header()]):
    if x_token != "fake-super-secret-token":
        raise HTTPException(status_code=400, detail="X-Token header invalid")
    

async def get_query_token(token: str):
    if token != "jessica":
        raise HTTPException(status_code=400, detail="No Jessica token provided")
    
    
cursorDep = Annotated[connection, Depends(get_connection)]