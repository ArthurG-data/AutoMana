from fastapi import APIRouter,  Response, HTTPException
from typing import Optional
from backend.database.get_database import cursorDep
from backend.new_services.ebay_management.services import register_scope

router = APIRouter(
    prefix='/scopes',
    responses={404:{'description' : 'Not found'}}
)

@router.post('/', description='add a new scope to the the available scope')
async def regist_scope(conn : cursorDep, scope: str, scope_description : Optional[str]):
    try:
        register_scope(conn, scope, scope_description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Cound not register scope: {e}')
    return Response(status_code=200, content='{scope} scope added')