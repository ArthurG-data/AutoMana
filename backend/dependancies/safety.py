from fastapi import HTTPException, Depends
from backend.core.settings import Settings, get_settings

def require_destructive_enabled():
    settings = get_settings()
    if not settings.ALLOW_DESTRUCTIVE_ENDPOINTS:
        raise HTTPException(status_code=403, detail="Destructive endpoints disabled in this environment.")