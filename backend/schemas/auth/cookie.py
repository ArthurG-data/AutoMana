from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class Cookies(BaseModel):
    session_id : str
    auth : bool
    user : str

class CookiesData(BaseModel):
    session_id : UUID
    ip_address : str
    user_agent : str
    expires_on : datetime