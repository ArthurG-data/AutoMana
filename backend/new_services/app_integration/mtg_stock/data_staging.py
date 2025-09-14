import os, json, io, logging
import pandas as pd
import pyarrow.parquet as pq
from backend.repositories.app_integration.mtg_stock.price_repository import PriceRepository
from pathlib import Path
import time

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

BASE = os.path.join(Path(__file__).resolve().parents[4], 'data/mtgstocks/raw/prints')

async def insert_card_identifiers():
    #initialisation process
    #await price_repository.rollback_transaction()
    try:
        for i, folder in enumerate(os.listdir(BASE), 1):
            try:
                pdir = os.path.join(BASE,folder)
                info_path = os.path.join(pdir, "info.json")
                logger.info("Processing: %s", info_path)
                id_dict = await process_info_file(info_path)
                # insert into dim_card_identifier if not exists
                # this is a bit tricky as we have multiple possible identifiers
                # we will use upsert with conflict on unique constraint
                # assuming you have a unique constraint on (source, source_id)
                # you may need to adjust this based on your actual schema
                query = """
                INSERT INTO dim_card_identifier (source, source_id, scryfall_id, multiverse_ids, tcg_id, cardtrader_id)
                VALUES 
                ('mtgstocks', %(mtgstock)s, %(scryfallId)s, %(multiverse_ids)s::jsonb, %(tcg_id)s, %(cardtrader_id)s)
                ON CONFLICT (source, source_id) DO UPDATE 
                SET scryfall_id = EXCLUDED.scryfall_id,
                    multiverse_ids = EXCLUDED.multiverse_ids,
                    tcg_id = EXCLUDED.tcg_id,
                    cardtrader_id = EXCLUDED.cardtrader_id
                """
                # execute the query using your database connection / ORM
                # e.g. await db.execute(query, id_dict)
            except Exception as e:
                logger.warning(f"Error processing folder: {folder} Error: {e}")
            if i % 100 == 0:
                logger.info(f"Processed {i} folders")
    finally:
        pass
        #await price_repository.rollback_transaction()

async def bulk_load(price_repository: PriceRepository, root_folder=BASE, batch_size=10000):
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
                id_dict = await process_info_file(info_path)
                price_df = await process_prices_file(price_path, id_dict)
                price_rows.append(price_df)
            except Exception as e:
                logger.warning(f"Error processing folder: {folder} Error: {e}")
            if i % batch_size == 0:
                big_price_df = pd.concat(price_rows, ignore_index=True)
                
                start = time.perf_counter()
                await price_repository.copy_prices(big_price_df)
                elapsed = time.perf_counter() - start
                logger.info("copy_prices took %.3f s for %d rows", elapsed, len(big_price_df))
                price_rows.clear()
            # flush leftovers
        if price_rows:
            big_price_df = pd.concat(price_rows, ignore_index=True)
            await price_repository.copy_prices(big_price_df)
    
        #start = time.perf_counter()
        #await price_repository.call_load_stage_from_raw()
        #elapsed = time.perf_counter() - start
        #logger.info("load_stage_from_raw took %.3f s", elapsed)
    #count = await price_repository.fetch_all_prices("stg_price_observation")
    #logger.info(f"Total rows in staging after load_stage_from_raw: {count}")
    #if count ==0:
    #    raise ValueError("No rows found in stg_price_observation table after load_stage_from_raw")
        #start = time.perf_counter()
        #await price_repository.call_load_dim_from_staging()
        #elapsed = time.perf_counter() - start
        #logger.info("load_dim_from_staging took %.3f s", elapsed)
    #count = await price_repository.fetch_all_prices("dim_price_observation")
    #logger.info(f"Total rows in staging after load_dim_from_staging: {count}")
    #if count ==0:
    #    raise ValueError("No rows found in dim_price_observation table after load_dim_from_staging")
        #start = time.perf_counter()
        #await price_repository.call_load_prices_from_dim()
        #elapsed = time.perf_counter() - start
        #logger.info("load_prices_from_dim took %.3f s", elapsed)
    finally:
        pass
        #await price_repository.drop_staging_table()
        #await price_repository.rollback_transaction()

