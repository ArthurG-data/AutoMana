
from fastapi import Depends, Request
from typing_extensions import Annotated
from backend.new_services.service_manager import ServiceManager

def extract_ip (request : Request)-> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0]  # Use the first IP
    else:
        ip = request.client.host
    return ip
    
ipDep = Annotated[str, Depends(extract_ip)]

def get_service_manager() -> ServiceManager:
    """Get the shared ServiceManager instance"""
    from backend.main import service_manager
    if service_manager is None:
        raise RuntimeError("ServiceManager not initialized")
    return service_manager
