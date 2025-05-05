
import urllib,  base64, httpx
from fastapi.responses import RedirectResponse
from backend.dependancies import  Settings
from backend.routers.ebay.utils import scopeDep


def login_ebay(settings : Settings, scopes : scopeDep):
    params = {
        "client_id": settings.ebay_client_id,
        "response_type": "code",
        "redirect_uri": settings.ebay_redirect_uri,
        "scope": " ".join(scopes),
        "secret" : settings.ebay_client_secret
    }

    auth_url = f"https://auth.ebay.com/oauth2/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url)

async def exange_auth(settings : Settings, code : str ):
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
