from pydantic import BaseModel
from uuid import UUID

class Token(BaseModel):
    access_token : str
    token_type : str

class TokenData(BaseModel):
    sub : str | None=None
    id : UUID
    role : str
    exp : int


class Cookies(BaseModel):
    session_id : str
    auth : bool
    user : str