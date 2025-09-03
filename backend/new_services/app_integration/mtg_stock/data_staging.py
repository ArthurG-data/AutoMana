import os, json, io, logging
import pandas as pd
import pyarrow.parquet as pq
from backend.repositories.app_integration.mtg_stock.price_repository import PriceRepository
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def process_info_file(path):
    with open(path, "r") as f:
        obj = json.load(f)
    return {
        "card_version_id": obj["scryfallId"],  # adjust key
    }

async def process_prices_file(path, card_version_id):
 
    df = pd.read_parquet(path)
    # normalize to match stg_price_obs schema
    df["card_version_id"] = card_version_id
    df['game_code'] =  "mtg"
    df['source_code'] = 'mtgstocks'
    df['scraped_at'] = pd.Timestamp.now()
    # you may already have ts_date / metric_code / etc in columns
    return df[["date","game_code", "card_version_id" ,"price_low", "price_avg",  "price_foil", "price_market", "price_market_foil", "source_code", "scraped_at"]]

BASE = os.path.join(Path(__file__).resolve().parents[4], 'data/mtgstocks/raw/prints')

async def bulk_load(price_repository: PriceRepository, root_folder=BASE, batch_size=10):
    price_rows = []
    #initialisation process
    #await price_repository.rollback_transaction()
    try:
        for i, folder in enumerate(os.listdir(BASE), 1):
            try:
                pdir = os.path.join(root_folder,folder)
                info_path = os.path.join(pdir, "info.json")
                price_path = os.path.join(pdir, "prices.parquet")
                logger.info("Processing: %s %s", info_path, price_path)
                card_id = await process_info_file(info_path)
                price_df = await process_prices_file(price_path, card_id.get("card_version_id"))
                price_rows.append(price_df)
            except Exception as e:
                logger.warning(f"Error processing folder: {folder} Error: {e}")
            if i % batch_size == 0:
                big_price_df = pd.concat(price_rows, ignore_index=True)
                await price_repository.copy_prices(big_price_df)
                count = await price_repository.fetch_all_prices("raw_mtg_stock_price")
                logger.info(f"Total rows in staging after batch: {count}")
                if count ==0:
                    raise ValueError("No rows found in staging table")
                logger.info(f"Inserted batch of {batch_size} folders")
                await price_repository.call_load_stage_from_raw()
                count = await price_repository.fetch_all_prices("stg_price_observation")
                logger.info(f"Total rows in staging after load_stage_from_raw: {count}")
                if count ==0:
                    raise ValueError("No rows found in stg_price_observation table after load_stage_from_raw")
                
                await price_repository.call_load_dim_from_staging()
                count = await price_repository.fetch_all_prices("dim_price_observation")
                logger.info(f"Total rows in staging after load_dim_from_staging: {count}")
                if count ==0:
                    raise ValueError("No rows found in dim_price_observation table after load_dim_from_staging")
                await price_repository.call_load_prices_from_dim()
                count = await price_repository.fetch_all_prices("price_observation")
                logger.info(f"Total rows in price_observation after load_prices_from_dim: {count}")
                if count ==0:
                    raise ValueError("No rows found in price_observation table after load_prices_from_dim")
                price_rows.clear()
            # flush leftovers
            if price_rows:
                big_price_df = pd.concat(price_rows, ignore_index=True)
                await price_repository.copy_prices(big_price_df)
    finally:
        pass
        #await price_repository.drop_staging_table()
        #await price_repository.rollback_transaction()

