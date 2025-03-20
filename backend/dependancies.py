from fastapi import Header, HTTPException, Depends
from typing_extensions import Annotated
from backend.database import connection, get_connection


async def get_token_header(x_token: Annotated[str, Header()]):
    if x_token != "fake-super-secret-token":
        raise HTTPException(status_code=400, detail="X-Token header invalid")

async def get_query_token(token: str):
    if token != "jessica":
        raise HTTPException(status_code=400, detail="No Jessica token provided")
    
cursorDep = Annotated[connection, Depends(get_connection)]