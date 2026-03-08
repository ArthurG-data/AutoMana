
from fastapi import Depends, Request
from typing import Annotated

def extract_ip (request : Request)-> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0]  # Use the first IP
    else:
        ip = request.client.host
    return ip
    
ipDep = Annotated[str, Depends(extract_ip)]

