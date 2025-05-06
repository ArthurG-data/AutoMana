
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from uuid import UUID
from backend.authentification import get_hash_password

class TokenInDb(BaseModel):
     user_id : UUID = Field(title='The ebay user_id')
     refresh_token : str
     aquired_on :datetime = Field(default_factory=datetime.now)
     expires_on : Optional[datetime] = None
     token_type : str

class InputEbaySettings(BaseModel):
    app_id: str
    response_type: str = Field(default="code", title="The type of auth")
    redirect_uri: str = Field(title="The URI field associated with the dev account")
    secret: str = Field(title="The raw secret for the eBay dev account")


    @model_validator(mode="after")
    def compute_hashed_secret(self) -> "InputEbaySettings":
        self.secret = get_hash_password(self.secret)
        return self