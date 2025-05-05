
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
     app_id : UUID
     client_id :str = Field(title='The ebay user_id')
     response_type: str = Field(default="code", title="The type of auth")
     redirect_uri: str = Field(title='The uri field associated to the dev account')
     scope: Optional[List[str]] = Field(exclude=True)
     secret : str  = Field(title='The secret associated to the ebay dev account')
     hashed_secret : Optional[str]= Field( default=None, exclude=True)

     @model_validator(mode='after')
     def hash_secret(cls, values):
          values.hashed_password = get_hash_password(values.secret)
          return values