

from fastapi import APIRouter
from backend.shared.dependancies import currentActiveSession

authentification_router = APIRouter(prefix='/auth')

@authentification_router.get('/sessions/')
async def test_function( session_id : currentActiveSession):
    return session_id

    
