
from fastapi import Depends, Request
from typing import Annotated

def extract_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0]
    elif request.client:
        ip = request.client.host
    else:
        ip = "unknown"
    return ip
    
ipDep = Annotated[str, Depends(extract_ip)]

