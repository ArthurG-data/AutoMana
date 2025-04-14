
from fastapi import APIRouter, Query, Depends
import urllib,  base64, httpx
from fastapi.responses import RedirectResponse
from backend.dependancies import get_settings, Settings
from typing import Annotated, Optional
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, timedelta
from uuid import UUID, uuid4

ebay_router = APIRouter(
    prefix='/ebay',
    tags=['ebay']
)

scopes = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory"
]



@ebay_router.get('/login')
def login_ebay(settings : Annotated[Settings, Depends(get_settings)]):
    
    params = {
        "client_id": settings.ebay_client_id,
        "response_type": "code",
        "redirect_uri": settings.ebay_redirect_uri,
        "scope": " ".join(scopes),
        "secret" : settings.ebay_client_secret
    }

    auth_url = f"https://auth.ebay.com/oauth2/authorize?{urllib.parse.urlencode(params)}"

    return RedirectResponse(url=auth_url)


class TokenInDb(BaseModel):
     user_id : UUID = Field(default_factory=uuid4)
     refresh_token : str
     aquired_on :datetime = Field(default_factory=datetime.now)
     expires_on : Optional[datetime] = None
     token_type : str
     refresh_token_expires_in : int  = Field(exclude=True)

     @model_validator( mode='after')
     def set_expiry(cls, values):
         values.expires_on = values.aquired_on +  timedelta(seconds=values.refresh_token_expires_in)
         return values
         



@ebay_router.get("/token", response_model=TokenInDb)
async def exange_auth(settings : Annotated[Settings, Depends(get_settings)], code : str = Query(...)):
    ci_cs = f"{settings.ebay_client_id}:{settings.ebay_client_secret}"
    encoded_ci_cs =ci_cs.encode()
    b64_e_ci_cs = base64.b64encode(encoded_ci_cs).decode()


    headers = {'Content-type' : 'application/x-www-form-urlencoded',
           'Authorization' : 'Basic ' + b64_e_ci_cs}
    
    data = {
        'grant_type' : 'authorization_code',
        'code' : code,
       "redirect_uri" : settings.ebay_redirect_uri
}
    async with httpx.AsyncClient() as client:
        res = await client.post(url='https://api.ebay.com/identity/v1/oauth2/token', headers=headers, data =data)
        res.raise_for_status()
        token_response = res.json()

    return token_response

@ebay_router.get('/settings')
async def get_settings(settings : Annotated[dict, Depends(get_settings)]):
    return settings