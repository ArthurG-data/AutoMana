from fastapi import Header, HTTPException, Depends, Request
from typing_extensions import Annotated
from functools import lru_cache
from backend.models.settings import PostgreSettings, GeneralSettings, EbaySettings


@lru_cache
def get_db_settings()->PostgreSettings:
    return PostgreSettings()

@lru_cache
def get_general_settings()->GeneralSettings:
    return GeneralSettings()

@lru_cache
def get_ebay_settings()->EbaySettings:
    return EbaySettings()


async def get_token_header(x_token: Annotated[str, Header()]):
    if x_token != "fake-super-secret-token":
        raise HTTPException(status_code=400, detail="X-Token header invalid")
    

async def get_query_token(token: str):
    if token != "jessica":
        raise HTTPException(status_code=400, detail="No Jessica token provided")

def extract_ip (request : Request)-> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0]  # Use the first IP
    else:
        ip = request.client.host
    return ip
    
ipDep = Annotated[str, Depends(extract_ip)]

