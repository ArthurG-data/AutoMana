from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
from datetime import datetime, timezone
import logging

from celery import chain
from automana.worker.main import run_service
from automana.worker.tasks.pipelines import mtgStock_download_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mtg_stock", tags=["mtg_stock"])

DEFAULT_BATCH_SIZE = 50
DEFAULT_DESTINATION = "/data/automana_data/mtgstocks/raw/prints/"


@router.post("/stage", status_code=status.HTTP_202_ACCEPTED)
async def stage_data():
    """Enqueue the MTGStock staging pipeline.

    Runs `mtgStock_download_pipeline`: reads pre-downloaded parquet/info
    files from disk into `pricing.raw_mtg_stock_price`, then promotes
    through `stg_price_observation` into `pricing.price_observation`.
    Returns immediately with a Celery task id; the actual work happens
    asynchronously on the worker."""
    try:
        result = mtgStock_download_pipeline.delay()
        return {"task_id": result.id, "status": "queued"}
    except Exception as e:
        logger.error("failed_to_enqueue_mtgstock_staging", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error enqueueing staging, {e}")


@router.post("/load_ids", status_code=status.HTTP_202_ACCEPTED)
async def load_full_scraper(
    batch_size: int = Query(DEFAULT_BATCH_SIZE),
    first_index: int = Query(1),
    market: str = Query("tcg"),
    destination_folder: str = Query(DEFAULT_DESTINATION),
):
    """Enqueue an MTGStocks API scraper run over ALL print IDs.

    Chain: start_run → run_full_load → finish_run. The scraper is
    intentionally long-running; the endpoint only enqueues."""
    try:
        run_key = f"mtgStock_full_load:{datetime.now(timezone.utc).date().isoformat()}"
        wf = chain(
            run_service.s(
                "ops.pipeline_services.start_run",
                pipeline_name="mtg_stock_full_load",
                source_name="mtgstocks",
                run_key=run_key,
            ),
            run_service.s(
                "mtg_stock.data_loader.run_full_load",
                destination_folder=destination_folder,
                batch_size=batch_size,
                first_index=first_index,
                market=market,
            ),
            run_service.s("ops.pipeline_services.finish_run", status="success"),
        )
        result = wf.apply_async()
        return {"task_id": result.id, "run_key": run_key, "status": "queued"}
    except Exception as e:
        logger.error("failed_to_enqueue_mtgstock_full_scrape", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error enqueueing full scrape, {e}")


@router.get("/load", status_code=status.HTTP_202_ACCEPTED)
async def load_selected_ids(
    print_ids: Optional[List[int]] = Query(None, description="A list of print IDs to fetch"),
    range_start: Optional[int] = Query(None, description="Start of the range of print IDs"),
    range_end: Optional[int] = Query(None, description="End of the range of print IDs"),
    batch_size: int = Query(DEFAULT_BATCH_SIZE),
    market: str = Query("tcg"),
    destination_folder: str = Query(DEFAULT_DESTINATION),
):
    """Enqueue an MTGStocks API scraper run over a specific list/range of print IDs.

    Accepts either `print_ids` (list) or `range_start`+`range_end`
    (inclusive). Chain: start_run → run_list_id_load → finish_run."""
    try:
        if not print_ids and (range_start is None or range_end is None):
            raise HTTPException(
                status_code=400,
                detail="You must provide either a list of print IDs or a range (range_start and range_end).",
            )
        if range_start is not None and range_end is not None:
            if range_start > range_end:
                raise HTTPException(
                    status_code=400,
                    detail="range_start must be less than or equal to range_end.",
                )
            print_ids = list(range(range_start, range_end + 1))

        run_key = f"mtgStock_selected:{datetime.now(timezone.utc).isoformat()}"
        wf = chain(
            run_service.s(
                "ops.pipeline_services.start_run",
                pipeline_name="mtg_stock_selected",
                source_name="mtgstocks",
                run_key=run_key,
            ),
            run_service.s(
                "mtg_stock.data_loader.run_list_id_load",
                destination_folder=destination_folder,
                batch_size=batch_size,
                ids_list=print_ids,
                market=market,
            ),
            run_service.s("ops.pipeline_services.finish_run", status="success"),
        )
        result = wf.apply_async()
        return {"task_id": result.id, "run_key": run_key, "queued_ids": len(print_ids)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("failed_to_enqueue_mtgstock_list_scrape", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error enqueueing list scrape, {e}")
