from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from backend.dependancies.service_deps import ServiceManagerDep
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mtg_stock", tags=["mtg_stock"])


@router.post("/stage")
async def stage_data(service_manager: ServiceManagerDep):
    try:
        await service_manager.execute_service("integration.mtg_stock.stage")

    except Exception as e:
        logger.error(f"Error staging data: {e}")
        raise HTTPException(status_code=500, detail=f"Error staging data, {e}")

@router.post("/load_ids")
async def load_ids(service_manager: ServiceManagerDep):
    try:
        await service_manager.execute_service("integration.mtg_stock.load_ids")

    except Exception as e:
        logger.error(f"Error loading IDs: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading IDs, {e}")

@router.get("/load")
async def get_print_data(  service_manager: ServiceManagerDep, print_ids: Optional[List[int]] = Query(None, description="A list of print IDs to fetch"),
                range_start: Optional[int] = Query(None, description="Start of the range of print IDs"),
                range_end: Optional[int] = Query(None, description="End of the range of print IDs"),
             ):
    # Logic to retrieve print data
    try:

        if not print_ids and (range_start is None or range_end is None):
            raise HTTPException(
                status_code=400,
                detail="You must provide either a list of print IDs or a range (range_start and range_end)."
            )

        # Handle range input
        if range_start is not None and range_end is not None:
            if range_start > range_end:
                raise HTTPException(
                    status_code=400,
                    detail="range_start must be less than or equal to range_end."
                )
            print_ids = list(range(range_start, range_end + 1))

        results = await service_manager.execute_service(
            "integration.mtg_stock.load",
            print_ids=print_ids,
            range_start=range_start,
            range_end=range_end
        )
        return {"data": results}
    except Exception as e:
        logger.error(f"Error fetching print data: {e}")
        return {"error": str(e)}
