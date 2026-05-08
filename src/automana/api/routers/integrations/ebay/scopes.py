from fastapi import APIRouter, Response, HTTPException
from typing import Literal, Optional
from automana.api.dependancies.database import cursorDep
from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.schemas.StandardisedQueryResponse import ApiResponse
from automana.core.services.app_integration.ebay.scope_service import register_scope

router = APIRouter(
    prefix='/scopes',
    responses={404: {'description': 'Not found'}}
)


@router.get('/', description='List all scopes available for a given eBay environment')
async def list_scopes(
    environment: Literal['SANDBOX', 'PRODUCTION'],
    service_manager: ServiceManagerDep,
):
    try:
        scopes = await service_manager.execute_service(
            "integrations.ebay.get_scopes_by_environment",
            environment=environment,
        )
        return ApiResponse(message="Scopes retrieved", data={"scopes": scopes})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not retrieve scopes: {e}")


@router.post('/', description='add a new scope to the the available scope')
async def regist_scope(conn: cursorDep, scope: str, scope_description: Optional[str]):
    try:
        register_scope(conn, scope, scope_description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Could not register scope: {e}')
    return Response(status_code=200, content='{scope} scope added')
