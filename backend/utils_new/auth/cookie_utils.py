
from  backend.schemas.auth.cookie import CookiesData
from uuid import UUID

def extract_session_id(cookies: CookiesData) -> UUID:
    if cookies and cookies.session_id:
        return UUID(cookies.session_id)
    return None