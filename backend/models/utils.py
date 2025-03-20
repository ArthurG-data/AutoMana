from pydantic import BaseModel


class Token(BaseModel):
    access_token : str
    token_type : str

class TokenData(BaseModel):
    username : str | None=None


class Cookies(BaseModel):
    session_id : str
    auth : bool
    user : str