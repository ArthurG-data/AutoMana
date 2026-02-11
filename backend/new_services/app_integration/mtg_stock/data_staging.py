import os, json,  logging
import pandas as pd
from backend.repositories.app_integration.mtg_stock.price_repository import PriceRepository
import time
from backend.core.service_registry import ServiceRegistry
from tqdm import tqdm
from backend.schemas.pipelines.mtg_stock import MTGStockBatchStep
from backend.repositories.ops.ops_repository import OpsRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def process_info_file(path):
    with open(path, "r") as f:
        obj = json.load(f)
    return {
        "mtgstock": obj["id"],
        "cardtrader": obj.get("cardtrader", None),
        "scryfallId": obj.get("scryfallId", None),
        "multiverse_ids": obj.get("multiverse_ids", None),
        "tcg_id": obj.get("tcg_id", None),
        "cardtrader_id": obj.get("cardtrader_id", None),
            # adjust key
    }

async def process_prices_file(path, id_dict):
 
    df = pd.read_parquet(path)
    # normalize to match stg_price_obs schema
    df["print_id"] = id_dict.get("mtgstock", None)
    df['game_code'] =  "mtg"
    df['source_code'] = 'mtgstocks'
    df['scraped_at'] = pd.Timestamp.now()
    # you may already have ts_date / metric_code / etc in columns
    return df[["date"
               ,"game_code"
               ,"print_id" 
               ,"price_low"
               ,"price_avg"
               ,"price_foil"
               ,"price_market"
               ,"price_market_foil"
               ,"source_code"
               ,"scraped_at"]]


@ServiceRegistry.register(
    path="mtg_stock.data_staging.bulk_load",
    db_repositories = ["price", "ops"],
)
async def bulk_load(price_repository: PriceRepository, ops_repository: OpsRepository, root_folder, batch_size=10000, ingestion_run_id: int = None):
    step_name = "bulk_load"
    price_rows = []
    batch_start = 0
    batch_end = 0
    batch_number = 1
    try:
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="running")
        for i, folder in tqdm(enumerate(os.listdir(root_folder), 1), desc="Processing MTG Stock folders", total=len(os.listdir(root_folder))):

            try:
                batch_end +=1
                pdir = os.path.join(root_folder,folder)
                info_path = os.path.join(pdir, "info.json")
                price_path = os.path.join(pdir, "prices.parquet")
                id_dict = await process_info_file(info_path)
                price_df = await process_prices_file(price_path, id_dict)
                price_rows.append(price_df)
            except Exception as e:
                logger.warning(f"Error processing folder: {folder} Error: {e}")
            if i % batch_size == 0:
                big_price_df = pd.concat(price_rows, ignore_index=True)
                start = time.perf_counter()
                #add update ingestion run status
                await price_repository.copy_prices_mtgstock(big_price_df)
                batch_start = batch_end
                elapsed = time.perf_counter() - start

                batch_result = MTGStockBatchStep(
                    ingestion_run_id=ingestion_run_id,
                    step_name=step_name,
                    batch_seq=batch_number,
                    range_start=batch_start,
                    range_end=batch_end,
                    items_ok=len(big_price_df),
                    items_failed=0,
                    status="success",
                    bytes_processed=big_price_df.memory_usage(deep=True).sum(),
                    duration_ms=int(elapsed * 1000),
                )
                await ops_repository.insert_batch_step(batch_result)
                batch_number += 1
                logger.info("copy_prices took %.3f s for %d rows", elapsed, len(big_price_df))
                price_rows.clear()
            # flush leftovers
        if price_rows:
            big_price_df = pd.concat(price_rows, ignore_index=True)
            await price_repository.copy_prices_mtgstock(big_price_df)
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="failed", error_details={"error": str(e)})
        raise e
    await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="success")

@ServiceRegistry.register(
    path="mtg_stock.data_staging.from_raw_to_staging",
    db_repositories = ["price", "ops"],
)
async def from_raw_to_staging(price_repository: PriceRepository
                              , ops_repository: OpsRepository
                              , ingestion_run_id: int):
    step_name = "raw_to_staging"
    await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="running")
    try:
        await price_repository.call_load_stage_from_raw()
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="success")
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="failed", error_details={"error": str(e)})
        raise e

@ServiceRegistry.register(
    path="mtg_stock.data_staging.from_staging_to_dim",
    db_repositories = ["price", "ops"],
)
async def from_staging_to_dim(price_repository: PriceRepository
                              , ops_repository: OpsRepository
                              , ingestion_run_id: int):
    step_name = "staging_to_dim"
    await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="running") 
    try:
        await price_repository.call_load_dim_from_staging()
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="success")
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="failed", error_details={"error": str(e)})
        raise e

@ServiceRegistry.register(
    path="mtg_stock.data_staging.from_dim_to_prices",
    db_repositories = ["price", "ops"],
)
async def from_dim_to_prices(price_repository: PriceRepository
                             , ops_repository: OpsRepository
                             , ingestion_run_id: int):
    step_name = "dim_to_prices"
    await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="running")
    try:
        await price_repository.call_load_prices_from_dim()
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="success")
    except Exception as e:
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="failed", error_details={"error": str(e)})
        raise e

async def insert_card_identifiers(card_repository, folder_path):
    try:
        ids = {}
        for i, folder in tqdm(enumerate(os.listdir(folder_path), 1), desc="Processing MTG Stock folders", total=len(os.listdir(folder_path))):
            try:
                pdir = os.path.join(folder_path, folder)
                info_path = os.path.join(pdir, "info.json")
                logger.info("Processing: %s", info_path)
                id_dict = await process_info_file(info_path)
                scry_id = id_dict.get("scryfallId", None)
                stock_id = id_dict.get("mtgstock", None)
                if scry_id and stock_id:
                    ids[scry_id] = stock_id
                else:
                    logger.warning(f"Missing scryfallId or mtgstock id in {info_path}")
                    continue
                # insert into dim_card_identifier if not exists
                # this is a bit tricky as we have multiple possible identifiers
                # we will use upsert with conflict on unique constraint
                # assuming you have a unique constraint on (source, source_id)
                # you may need to adjust this based on your actual schema


            except Exception as e:
                logger.warning(f"Error processing folder: {folder} Error: {e}")
            ids = {str(k): str(v) for k, v in ids.items() if k and v}  # filter out None values
        await card_repository.bulk_update_mtg_stock_ids(ids)
    finally:
        pass
        #await price_repository.rollback_transaction()
