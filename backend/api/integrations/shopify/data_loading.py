from fastapi import APIRouter, Depends, HTTPException, Query
from backend.new_services.service_manager import ServiceManager
from backend.dependancies.general import get_service_manager

data_loading_router = APIRouter(prefix="/data_loading", tags=["Shopify Data Loading"])

@data_loading_router.post("/load_data")
async def load_data(PATH_TO_JSON: str = Query(...), market_code: str = Query(...), output_path: str = Query(...), service_manager: ServiceManager = Depends(get_service_manager)):
    try:
        await service_manager.execute_service(
            "integration.shopify.load_data",
            path_to_json=PATH_TO_JSON,
            market_code=market_code,
            output_path=output_path
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
