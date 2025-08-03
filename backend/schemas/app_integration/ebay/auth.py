from typing import Optional, List, Dict
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, timedelta
from uuid import UUID
from backend.utils_new.auth import get_hash_password
import base64

class HeaderApi(BaseModel):
    site_id: str = Field(default="0", alias="X-EBAY-API-SITEID")
    compatibility_level: str = Field(default="967", alias="X-EBAY-API-COMPATIBILITY-LEVEL")
    call_name: str = Field(default="GetMyeBaySelling", alias="X-EBAY-API-CALL-NAME")
    iaf_token: str = Field(..., alias="X-EBAY-API-IAF-TOKEN")
    class Config:
        populate_by_name = True 
        
class AuthHeader(BaseModel):
    app_id : str 
    secret : str 
    authorization : Optional[str] = None

    @model_validator(mode='after')
    def encode_authorisation(self) -> "AuthHeader":
        ci_cs = f"{self.app_id}:{self.secret}"
        encoded_ci_cs =ci_cs.encode()
        b64_e_ci_cs = base64.b64encode(encoded_ci_cs).decode()
        self.authorization = 'Basic ' + b64_e_ci_cs
        return self
    
    def to_header(self) -> dict:
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": self.authorization
        }


class TokenRequestData(BaseModel):
    grant_type: str

    def to_data(self) -> Dict[str, str]:
        raise NotImplementedError("Subclasses must implement to_data()")
    
class AuthData(TokenRequestData):
   
    code : str
    redirect_uri : str

    def __init__(self, **data):
        data['grant_type'] = 'authorization_code'
        super().__init__(**data)

    def to_data(self)->dict:
        return {
            'grant_type' : self.grant_type,
            'code' : self.code,
            "redirect_uri" : self.redirect_uri
        }
    
class ExangeRefreshData(TokenRequestData):
    token : str
    scope : List[str]

    def __init__(self, **data):
        data['grant_type'] = 'refresh_token'
        super().__init__(**data)


    def to_data(self)->dict:
        return {
            'grant_type' : self.grant_type,
            "refresh_token": self.token ,
            'scope' : " ".join(self.scope)
        }

class TokenResponse(BaseModel):
    access_token : str
    expires_in : int
    expires_on: Optional[datetime] = None  
    refresh_token : Optional[str]=None
    acquired_on :datetime = Field(default_factory=datetime.now)
    refresh_token_expires_in : Optional[int]=None 
    token_type : str
    refresh_expires_on: Optional[datetime] = None 
    @model_validator(mode='after')
    def compute_expires_on(self) -> "TokenResponse":
        if self.refresh_token_expires_in is not None:
            self.refresh_expires_on = self.acquired_on + timedelta(seconds=self.refresh_token_expires_in)
        if self.expires_in is not None:
            self.expires_on = self.acquired_on + timedelta(seconds=self.expires_in)
        return self


class InputEbaySettings(BaseModel):
    app_id: str
    response_type: str = Field(default="code", title="The type of auth")
    redirect_uri: str = Field(title="The URI field associated with the dev account")
    secret: str = Field(title="The raw secret for the eBay dev account")


    @model_validator(mode="after")
    def compute_hashed_secret(self) -> "InputEbaySettings":
        self.secret = get_hash_password(self.secret)
        return self