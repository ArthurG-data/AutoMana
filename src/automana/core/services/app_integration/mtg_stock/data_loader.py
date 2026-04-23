import json, logging, os
from typing import  List
from pathlib import Path
import pandas as pd
import pyarrow as pa, pyarrow.parquet as pq
from automana.core.repositories.app_integration.mtg_stock.ApiMtgStock_repository import ApiMtgStockRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.models.pipelines.mtg_stock import MTGStockBatchStep
from tqdm import tqdm

logger = logging.getLogger(__name__)

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
        destination_folder: str,
        market:str = "tcg"
    ):
    try:
        for item in result:
            pdir = destination_folder / str(item.get('card_id'))
            pdir = Path(pdir)
            pdir.mkdir(parents=True, exist_ok=True)
            data = item.get('data', None)
            details = data.get('details', None) if data else None
            prices = data.get('prices', None) if data else None
            if details:
                info_path = pdir / "info.json"
                info_path.write_bytes(details)
            if prices:
                price_path = pdir  / f"prices.{market}.parquet"
                # `prices_to_parquet` both decodes the JSON and writes the
                # parquet file; no prior `write_bytes(prices)` needed.
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
        market: str = "tcg",
        ):
    step_name = "mtgStock_data_loader"
    processed = 0
    errored = 0
    step = 1
    #first, download all new prices for prints with existing data
    existing_ids = get_existing_ids(destination_folder)
    logger.info(f"Found {len(existing_ids)} existing print IDs to update prices for.")
    logger.info(f"First index passed: {first_index}")
    start_index = existing_ids.index(first_index) if first_index in existing_ids else 0
    logger.info(f"Starting price updates from index {start_index} (print ID {existing_ids[start_index] if existing_ids else 'N/A'})")
    total_prints = len(existing_ids)
    batch_result = None
    end = start_index

    if ops_repository and ingestion_run_id is not None:
        await ops_repository.update_run(
            ingestion_run_id, status="running", current_step=step_name,
        )

    try:
        while start_index < total_prints:
            end = min(start_index + batch_size , total_prints)
            batch_ids = existing_ids[start_index:end]
            batch_result = await mtg_stock_repository.fetch_card_price_data_batch(
                                      card_ids=batch_ids, market=market)
            logger.info(f"Updating prices for print IDs {batch_ids[0]} to {batch_ids[-1]}, {batch_result.get('items_ok', 0)} succeeded, {batch_result.get('items_failed', 0)} failed")
            cleaned_data = [d for d in batch_result.get("data", []) if "error" not in d]
            await write_batch(cleaned_data, Path(destination_folder), market=market)
            start_index =  end
    except Exception as e:
        # Prior version referenced an undefined `end_index` here and masked the
        # real exception with a NameError. `end` is the local batch bound.
        logger.error(f"Error updating prices: {e}")
        if existing_ids and start_index < total_prints:
            processed, errored, step = await end_of_batch_process(
                ops_repository,
                ingestion_run_id,
                step_name,
                step,
                existing_ids[start_index],
                existing_ids[min(end, total_prints) - 1],
                processed,
                errored,
                batch_result,
            )
        if ops_repository and ingestion_run_id is not None:
            await ops_repository.update_run(
                ingestion_run_id,
                status="failed",
                current_step=step_name,
                error_details={"error": str(e)},
            )
        raise
    #then, process all remaining prints in batches

    last_existing_id = await get_last_print_id(mtg_stock_repository, max(existing_ids) if existing_ids else 0)
    logger.info(f"New prints added until {last_existing_id}, starting full load from {max(existing_ids)+1 if existing_ids else 1}")
    total_prints = last_existing_id
    try:
        start_from = (existing_ids[-1] + 1) if existing_ids else 1
        for start in range(start_from, last_existing_id + 1, batch_size):
            end = min(start + batch_size - 1, total_prints)
            # `fetch_card_price_data_batch` signature is (card_ids, market).
            # The prior implementation passed non-existent kwargs and raised
            # TypeError on the first call.
            batch_ids = list(range(start, end + 1))
            batch_result = await mtg_stock_repository.fetch_card_price_data_batch(
                card_ids=batch_ids, market=market,
            )
            cleaned_data = [d for d in batch_result.get("data", []) if "error" not in d]
            await write_batch(cleaned_data, Path(destination_folder), market=market)
            processed, errored, step = await end_of_batch_process(
                ops_repository,
                ingestion_run_id,
                step_name,
                step,
                start,
                end,
                processed,
                errored,
                batch_result,
            )
        if ops_repository and ingestion_run_id is not None:
            await ops_repository.update_run(
                ingestion_run_id,
                status="success",
                current_step=step_name,
                notes=f"Processed {processed} items with {errored} errors.",
            )
    except Exception as e:
        if ops_repository and ingestion_run_id is not None:
            await ops_repository.update_run(
                ingestion_run_id,
                status="failed",
                current_step=step_name,
                error_details={"error": str(e)},
            )
        raise
    return {"processed": processed, "errored": errored}

@ServiceRegistry.register(
        "mtg_stock.data_loader.run_list_id_load",
        api_repositories=["mtg_stock"],
        db_repositories=["ops"]
)
async def run_mtgstock_pipeline_selected_lists(
        mtg_stock_repository : ApiMtgStockRepository,
        destination_folder: str,
        ingestion_run_id: int,
        batch_size: int,
        ids_list: List[int],
        ops_repository : OpsRepository | None = None,
        market: str = "tcg"):
    step_name = "mtgStock_data_loader"
    processed = 0
    errored = 0
    step = 1

    start_index =0
    total_prints = len(ids_list)

    pbar = tqdm(total=total_prints, desc=f"MTGStocks ({market})", unit="cards", dynamic_ncols=True)

    if ops_repository and ingestion_run_id is not None:
        await ops_repository.update_run(
            ingestion_run_id, status="running", current_step=step_name,
        )

    try:
        while start_index < total_prints:
            end_index = min(start_index + batch_size , total_prints)
            batch_ids = ids_list[start_index:end_index]

            pbar.set_postfix_str(
                f"step={step} range_idx={start_index}-{end_index-1} "
                f"id={batch_ids[0]}..{batch_ids[-1]} ok={processed} err={errored}"
            )
            batch_result_data = await mtg_stock_repository.fetch_card_price_data_batch(
                                    card_ids=batch_ids,
                                    market=market)
            #remove the errored ones before writing and processing results
            cleaned_data = [d for d in batch_result_data.get("data", []) if "error" not in d]

            await write_batch(cleaned_data, Path(destination_folder), market=market)
            processed, errored, step = await end_of_batch_process(
                ops_repository=ops_repository,
                ingestion_run_id=ingestion_run_id,
                step_name=step_name,
                step=step,
                start=ids_list[start_index],
                end=ids_list[end_index-1],
                processed=processed,
                errored=errored,
                batch_run_result=batch_result_data,
            )

            pbar.update(end_index - start_index)
            start_index = end_index
            pbar.set_postfix_str(f"done ok={processed} err={errored}")

        if ops_repository and ingestion_run_id is not None:
            await ops_repository.update_run(
                ingestion_run_id,
                status="success",
                current_step=step_name,
                notes=f"Processed {processed} items with {errored} errors.",
            )

        return {"status": "success", "processed": processed, "errored": errored}
    except Exception as e:

        pbar.set_postfix_str(f"FAILED ok={processed} err={errored}")
        pbar.close()
        logger.error(f"Error updating prices: {e}")
        if ops_repository and ingestion_run_id is not None:
            await ops_repository.update_run(
                ingestion_run_id,
                status="failed",
                current_step=step_name,
                error_details={"error": str(e)},
            )
        raise
    finally:
        pbar.close()

async def end_of_batch_process(ops_repository,
                               ingestion_run_id,
                               step_name,
                               step,
                               start,
                               end,
                               processed=0,
                               errored=0,
                               batch_run_result=None):
    """Record one batch into ops and advance the running counters."""
    items_ok = batch_run_result.get("items_ok", 0) if batch_run_result else 0
    items_failed = batch_run_result.get("items_failed", 0) if batch_run_result else 0
    bytes_processed = batch_run_result.get("bytes_processed", 0) if batch_run_result else 0
    batch_data = batch_run_result.get("data", []) if batch_run_result else []

    processed += items_ok
    errored += items_failed

    if ops_repository and ingestion_run_id is not None:
        batch_step = MTGStockBatchStep(
            ingestion_run_id=ingestion_run_id,
            batch_seq=step,
            step_name=step_name,
            range_start=start,
            range_end=end,
            total_in_batch=len(batch_data),
            status="success" if items_failed == 0 else "partial",
            items_ok=items_ok,
            items_failed=items_failed,
            bytes_processed=bytes_processed,
            duration_ms=batch_run_result.get("duration_ms", 0.0) if batch_run_result else 0.0,
            error_code=batch_run_result.get("error_code") if batch_run_result else None,
            error_details=batch_run_result.get("error_details") if batch_run_result else None,
        )
        await ops_repository.insert_batch_step(batch_step=batch_step)
        await ops_repository.update_run(
            ingestion_run_id,
            status="running",
            current_step=step_name,
            notes=f"Processed {processed} items with {errored} errors.",
        )

    step += 1
    return processed, errored, step





