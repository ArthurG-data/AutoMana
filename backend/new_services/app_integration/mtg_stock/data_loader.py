import json, logging, os
from typing import  List
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import pyarrow as pa, pyarrow.parquet as pq
from backend.repositories.app_integration.mtg_stock.ApiMtgStock_repository import ApiMtgStockRepository
from backend.core.service_registry import ServiceRegistry
from backend.repositories.ops.ops_repository import OpsRepository
from backend.schemas.pipelines.mtg_stock import MTGStockBatchStep

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

#utils
def prices_to_parquet(print_id: int, raw_json: bytes, out_path: Path):
    obj = json.loads(raw_json)
    # obj has arrays like {"low": [[ts, price], ...], "avg": [...], "high": [...], "foil": [...]?}
    def series(name):
        arr = obj.get(name) or []
        if not arr: return pd.DataFrame(columns=["date", name])
        df = pd.DataFrame(arr, columns=["ts_ms", name])
        df["date"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.date
        return df[["date", name]]

    df = series("low").merge(series("avg"), on="date", how="outer") \
                      .merge(series("foil"), on="date", how="outer") \
                      .merge(series("market"), on="date", how="outer") \
                      .merge(series("market_foil"), on="date", how="outer")

    if df.empty:
        df = pd.DataFrame(columns=["date","price_low","price_avg","price_foil","price_market", "price_market_foil"])
    else:
        df = df.rename(columns={"low":"price_low","avg":"price_avg","foil":"price_foil", "market":"price_market", "market_foil":"price_market_foil"})
        df = df.sort_values("date").drop_duplicates("date", keep="last")
    df.insert(0, "print_id", print_id)
    table = pa.Table.from_pandas(df, preserve_index=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_path)


async def write_batch(
        result: list,
        destination_folder: str
    ):
    try:
        for item in result:
            pdir = destination_folder / str(item.get('card_id'))
            pdir.mkdir(parents=True, exist_ok=True)
            details = item.get('details', None)
            prices = item.get('prices', None)
            if details:
                info_path = pdir / "info.json"
                info_path.write_bytes(details)
            if prices:
                price_path = pdir  / "prices.parquet"
                price_path.write_bytes(prices)
                prices_to_parquet(item.get('card_id'), prices, price_path)
    except Exception as e:
        logger.error(f"Error writing batch: {e}")

def get_existing_ids(
        destination_folder: str
    )-> List[int]:
    file_name = "existing_ids.json"
    base_path = Path(destination_folder)
    list_path = base_path / file_name
    logger.info(f"Checking existing IDs in {base_path}")

    if list_path.exists():
        try:
            ids = json.loads(list_path.read_text())
            ids = sorted(int(x) for x in ids)
            return ids
        except Exception as e:
            logger.warning("Failed to read %s (%s); falling back to directory scan", list_path, e)
    else:
        ids = []


    if not base_path.exists():
        return ids

    with os.scandir(base_path) as it:
        for entry in it:
            if not entry.is_dir():
                continue
            if not entry.name.isdigit():
                continue
            # delete empty directories
            if len(os.listdir(entry.path)) == 0:
                os.rmdir(entry.path)
                continue
            ids.append(int(entry.name))
    with open(list_path, "w") as f:
        json.dump(sorted(ids), f)
    return sorted(set(ids))

async def id_exists(repo: ApiMtgStockRepository, cid: int) -> bool:
    return await repo.fetch_card_details(cid) is not None  # fetch_card_details returns None on 404

async def get_last_print_id(
       mtg_stock_repository : ApiMtgStockRepository,
       last_known: int
    ) -> int:
    #get the last print id available in the website

    lo = last_known
    # If last_known is missing (schema drift), walk down until you hit an existing ID or 1.
    while lo > 1 and not await id_exists(mtg_stock_repository, lo):
        lo -= 1

    hi = lo + 1
    # Exponential step until you hit a 404
    while await id_exists(mtg_stock_repository, hi):
        lo, hi = hi, hi * 2

    # Binary search between last existing (lo) and first missing (hi)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if await id_exists(mtg_stock_repository, mid):
            lo = mid
        else:
            hi = mid
    return lo
    

@ServiceRegistry.register(
        "mtg_stock.data_loader.run_full_load",
        api_repositories=["mtg_stock"],
        db_repositories=["ops"]
)
#main service to run full load
async def run_mtgstock_pipeline(
        mtg_stock_repository : ApiMtgStockRepository,
        destination_folder: str,
        ingestion_run_id: int,
        batch_size: int,
        first_index: int = 1,
        ops_repository : OpsRepository | None = None,
        run_key: str | None = None
        , celery_task_id: str | None = None):
    #need to insert each batch
    #need to update step status at the end and beginning
    processed = 0 
    errored = 0
    step = 1
    '''
    run key ois not a vaild argument here, it is set in the pipeline task
    await ops_repository.update_run(
            run_key=run_key,
            status="running",
            current_step="mtgStock_data_loader",
            celery_task_id=celery_task_id
        )
    '''
    #first, download all new prices for prints with existing data
    existing_ids = get_existing_ids(destination_folder)
    logger.info(f"Found {len(existing_ids)} existing print IDs to update prices for.")
    start_index = existing_ids.index(first_index) if first_index in existing_ids else 0
    logger.info(f"Starting price updates from index {start_index} (print ID {existing_ids[start_index] if existing_ids else 'N/A'})")
    total_prints = len(existing_ids)
    try:
        while start_index < total_prints:
            end = min(start_index + batch_size , total_prints)
            batch_ids = existing_ids[start_index:end]
            batch_result = await mtg_stock_repository.fetch_card_price_data_batch(
                                      card_ids=batch_ids)
            logger.info(f"Updating prices for print IDs {batch_ids[0]} to {batch_ids[-1]}, {batch_result.get('items_ok', 0)} succeeded, {batch_result.get('items_failed', 0)} failed")
            cleaned_data = [d for d in batch_result.get("data", []) if "error" not in d]
            await write_batch(cleaned_data, Path(destination_folder))
            start_index =  end
    except Exception as e:
        logger.error(f"Error updating prices: {e}")
        return
        processed, errored, step = await end_of_batch_process(ops_repository
                                                                  , ingestion_run_id
                                                                  , step
                                                                  , existing_ids[start_index]
                                                                  , existing_ids[end_index-1],
                                                                    run_key, celery_task_id
                                                                    ,processed
                                                                    ,errored
                                                                    , batch_result)
        start_index += batch_size
        end_index += batch_size
    #then, process all remaining prints in batches

    last_existing_id = await get_last_print_id(mtg_stock_repository, max(existing_ids) if existing_ids else 0)
    total_prints = last_existing_id
    try:
        for start in range(existing_ids[-1] +1, last_existing_id + 1, batch_size):
            end = min(start + batch_size - 1, total_prints)
            batch_result = await mtg_stock_repository.fetch_card_data_batches(
                                      range_start=start,
                                      range_end=end,
                                      batch_size=batch_size,
                                      destination_folder=destination_folder,
                                      print_ids=None)
            
            cleaned_data = [d for d in batch_result.get("data", []) if "error" not in d]
            await write_batch(cleaned_data, Path(destination_folder))
            processed, errored, step = await end_of_batch_process(ops_repository
                                                                    , ingestion_run_id
                                                                    , step
                                                                    , start
                                                                    , end,
                                                                        run_key, celery_task_id
                                                                        ,processed
                                                                        ,errored
                                                                        , batch_result)
        await ops_repository.update_run(
            run_key=run_key,
            status="success",
            ended_at=datetime.now(timezone.utc),
            current_step="mtgStock_data_loader",
            celery_task_id=celery_task_id,
            notes=f"Processed {processed} items with {errored} errors."
        )
    except Exception as e:
        await ops_repository.update_run(
            run_key=run_key,
            status="failed",
            current_step="mtgStock_data_loader",
            celery_task_id=celery_task_id,
            error_details={"error": str(e)}

        )

async def end_of_batch_process(ops_repository,  ingestion_run_id, step, start, end, run_key, celery_task_id, processed, errored, batch_run_result = None):
        
    batch_result: MTGStockBatchStep = MTGStockBatchStep(
            ingestion_run_id=ingestion_run_id,
            batch_seq=step,
            range_start=start,
            range_end=end,
            status=batch_run_result.get("status", "failed"),
            items_ok=batch_run_result.get("items_ok", 0),
            items_failed=batch_run_result.get("items_failed", end-start +1 - batch_run_result.get("items_ok", 0)),
            bytes_processed=batch_run_result.get("bytes_processed", 0),
            duration_ms=batch_run_result.get("duration_ms", 0.0),
            error_code=batch_run_result.get("error_code"),
            error_details=batch_run_result.get("error_details")
        )
    processed += batch_run_result.get("items_ok", 0)
    errored += batch_run_result.get("items_failed", end-start +1 - batch_run_result.get("items_ok", 0))
    await ops_repository.insert_batch_step(batch_step=batch_result)
    step += 1
    await ops_repository.update_run(
        run_key=run_key,
        status="success",
        ended_at=datetime.now(timezone.utc),
        current_step="mtgStock_data_loader",
        celery_task_id=celery_task_id,
        notes=f"Processed {processed} items with {errored} errors."
    )
    return processed, errored, step





