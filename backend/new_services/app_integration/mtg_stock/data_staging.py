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
    df['source_code'] = 'mtg_stock'
    # you may already have ts_date / metric_code / etc in columns
    return df[["date","game_code", "card_version_id" ,"price_low", "price_avg",  "price_foil", "price_market", "price_market_foil", "source_code"]]

BASE = os.path.join(Path(__file__).resolve().parents[4], 'data/mtgstocks/raw/prints')

async def bulk_load(price_repository: PriceRepository, root_folder=BASE, batch_size=10):
    price_rows = []
    #initialisation process
    await price_repository.rollback_transaction()
    await price_repository.create_staging_table()
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
                logger.warning("Error processing folder: %s Error: %s", folder, e)
            if i % batch_size == 0:
                big_price_df = pd.concat(price_rows, ignore_index=True)
                await price_repository.copy_prices(big_price_df)
                """
                # merge staging into final tables
                with conn.cursor() as cur:
                    cur.execute("CALL load_prints_from_staging();")
                    cur.execute("CALL load_prices_from_staging();")
                conn.commit()
                """
                #info_rows.clear()
                price_rows.clear()
            # flush leftovers
            if price_rows:
                big_price_df = pd.concat(price_rows, ignore_index=True)
                await price_repository.copy_prices(big_price_df)
    finally:
        pass
        #await price_repository.drop_staging_table()
        #await price_repository.rollback_transaction()

