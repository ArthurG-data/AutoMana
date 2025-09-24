import json
import os,  glob, ijson, functools, requests
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Any, Optional, Tuple
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv
from backend.schemas.external_marketplace.shopify import shopify_theme
from backend.repositories.app_integration.shopify.product_repository import ProductRepository

@functools.lru_cache(maxsize=365)
def fetch_fx_rate(from_currency: str, to_currency: str, date_str: str, app_id : str) -> float:
    
    # example using exchangerate.host
    resp = requests.get(
        f"https://openexchangerates.org/api/historical/{date_str}.json" ,
        params={"app_id": app_id },
        timeout=5,
    )
    resp.raise_for_status()
    from_rate = resp.json()["rates"][from_currency]
    to_rate = resp.json()["rates"][to_currency]
    rate = to_rate / from_rate
    return rate

async def get_market_id(market_repository ,code : str)-> int:
    try:
        market_id = await market_repository.get_market_code(code)
        if market_id is not None:
            return market_id
        else:
            return -1
    except Exception as e:
        print(f"Error fetching market_id for {code}: {e}")
        return -1

def prepare_product_shop_id_query(validated_batch: shopify_theme.BatchProductProces) -> Tuple[
    list[str],
    list[str],
    list[int],
    list[datetime],
    list[datetime]
]:
    p_product_shop_ids : List[str] = []
    p_product_ids : List[str] = []
    p_market_ids : List[int] = []
    p_created_at : List[datetime] = []
    p_updated_at : List[datetime] = []
    for product in validated_batch:
        p_product_shop_ids.append(product.product_shop_id)
        p_product_ids.append(str(product.product_id))
        p_market_ids.append(product.shop_id)
        p_created_at.append(product.created_at)
        p_updated_at.append(product.updated_at) 
    
    return (p_product_shop_ids, p_product_ids, p_market_ids, p_created_at, p_updated_at  ) 


def validate_batch(batch: List[Any]) -> shopify_theme.BatchProductProces:
    validated_batch = []
    for idx ,item in enumerate(batch):
        try:
            product : shopify_theme.ProductPrice = shopify_theme.ProductPrice.model_validate(item)
            validated_batch.append(product)
        except Exception as e:
            raise ValueError(f"Validation error in item {item}: {e}")
    return shopify_theme.BatchProductProces(items=validated_batch)
             
async def bulk_insert_product(batch: Tuple [
    List[datetime], 
    List[int],
    List[Decimal],
    list[str],
    list[Decimal],
    list[str]
], repository: ProductRepository):
    await repository.bulk_insert_products( batch)


async def bulk_insert_prices(batch: Tuple[
    List[datetime],
    List[str],
    List[Decimal],
    List[str],
    List[Decimal],
    List[bool],
    List[str]
      ], repository: ProductRepository):

    await repository.bulk_insert_prices(batch)

def find_condition_variant(product: shopify_theme.ProductModel, condition: str) -> Optional[float]:
    """
    Find the price of a variant with the specified condition in the product.
    Returns None if no such variant exists.
    """
    for v in product.variants:
        if condition.lower() in v.title.lower():
            return v.price
    return None


def stream_json_file(path: str, market_id: str, app_id: str, batch_size: int = 1000, product_currency='AUD'):
    """
    Stream and yield validated batches of ProductPrice from a JSON file.
    Does not perform DB upload; just yields the validated batch for further processing.
    """
    with open(path, 'r', encoding='utf-8') as file:
        batch = []
        items = ijson.items(file, 'items.item')
        products_model = [shopify_theme.ProductModel(**c) for c in items ]
        for obj in products_model: 
            date = obj.updated_at.date().isoformat() 
            exange_rate = fetch_fx_rate(product_currency, 'USD', date, app_id)
            batch.append(
                {
                    'product_id': obj.id,
                    'shop_id': market_id,
                    'price': find_condition_variant(obj, "Near Mint"),
                    'price_usd': Decimal(find_condition_variant(obj, "Near Mint")) * Decimal(exange_rate),
                    'foil_price':find_condition_variant(obj, "Near Mint Foil"),
                    'foil_price_usd': Decimal(find_condition_variant(obj, "Near Mint Foil")) * Decimal(exange_rate) if find_condition_variant(obj, "Near Mint Foil") else None,
                    'html_body': obj.body_html,
                    'currency': product_currency,
                    'created_at': obj.created_at,
                    'updated_at': obj.updated_at,
                    'source': 'test_source'
                }
            )
            if len(batch) >= batch_size:
                validated_batch = validate_batch(batch)
                yield validated_batch
                batch.clear()
        if batch:
            validated_batch = validate_batch(batch)
            yield validated_batch

# New function to upload batches yielded by the stream

async def upload_batches_from_stream(path: str, market_id: str, app_id: str, repository: ProductRepository, batch_size: int = 1000, product_currency='AUD'):
    for validated_batch in stream_json_file(path, market_id, app_id, batch_size, product_currency):
        #
        """
        prepared_product_input = prepare_product_shop_id_query(validated_batch)
        try:
            bulk_insert_product(prepared_product_input, conn)
        except Exception as e:
            print(f"Error during bulk insert: {e}")
            raise
        normal_batch, foil_batch = validated_batch.prepare_price_batches(include_foil=True)
     
        try:
            bulk_insert_prices(normal_batch, conn)
            if foil_batch is not None:
                bulk_insert_prices(foil_batch, conn)

        except Exception as e:
            print(f"Error during bulk insert: {e}")
            raise
        """

        await insert_card_product_reference(validated_batch, repository)

async def upload_all_json_in_directory(absolute_path: str, market_id: str, app_id: str, repository: ProductRepository, batch_size: int = 1000, product_currency='AUD'):
    """
    Iterate over all .json files in a directory and upload their contents to the DB in batches.
    Shows a tqdm progress bar for file processing, keeping the bar at the same location.
    """
    # Ensure the path is absolute
    abs_directory_path = os.path.abspath(absolute_path)
    
    # Verify the directory exists
    if not os.path.exists(abs_directory_path):
        raise FileNotFoundError(f"Directory not found: {abs_directory_path}")
    
    if not os.path.isdir(abs_directory_path):
        raise NotADirectoryError(f"Path is not a directory: {abs_directory_path}")
    
    # Find all JSON files in the absolute directory path
    json_files = glob.glob(os.path.join(abs_directory_path, '*.json'))
    
    if not json_files:
        print(f"No JSON files found in directory: {abs_directory_path}")
        return
    
    print(f"Found {len(json_files)} JSON files in: {abs_directory_path}")
    
    with tqdm(json_files, desc="Processing JSON files", dynamic_ncols=True, leave=True) as pbar:
        for path in pbar:
            pbar.set_postfix_str(f"{os.path.basename(path)}")
            try:
                upload_batches_from_stream(path, market_id, app_id, repository, batch_size, product_currency)
            except Exception as e:
                print(f"Error processing {path}: {e}")

async def insert_card_product_reference(batch: shopify_theme.BatchProductProces, repository: ProductRepository):

    await repository.insert_card_product_reference(batch.prepare_prodcut_card_batches())


from fastparquet import write, ParquetFile
from pathlib import Path
from zoneinfo import ZoneInfo

AUS_TZ = ZoneInfo("Australia/Brisbane")

def _to_utc(x):
    if x is None or x == "":
        return pd.NaT
    return pd.to_datetime(x, utc=True, errors="coerce")

def _current_local_date():
    # Local date in Australia/Brisbane, stored as a date (no time)
    return pd.Timestamp(datetime.now(AUS_TZ).date())

# --- helper: build long-format rows for one product (snapshot = now) ---
def _df_from_item(item: dict) -> pd.DataFrame:
    """
    Build one row per (date, variation) with price.
    Columns: date, variation, price, _src_updated_at (for dedupe then dropped)
    """
    variants = item.get("variants", []) or []
    if not variants:
        return pd.DataFrame(columns=["product_id", "date", "variation", "price"])

    local_date = _current_local_date()

    rows = []
    for v in variants:
        rows.append({
            "product_id": item.get("id"),
            "date":  _to_utc(v.get("updated_at")),
            "variation": v.get("title"),
            "price": float(v["price"]) if v.get("price") is not None else None,
            "scraped_at": local_date
        })

    df = pd.DataFrame(rows, columns=["product_id", "date", "variation", "price", "scraped_at"])
    # Dtypes
    df["product_id"] = df["product_id"].astype("int64")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], utc=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").astype("float64")
    #shrink memory
    df["variation"] = df["variation"].astype("category")
    return df[["product_id","date","variation","price","scraped_at"]]

def _row_group_offsets(n_rows: int, group_size: int) -> list[int]:
    """Fastparquet wants starting indices of each row group."""
    if group_size <= 0 or n_rows <= group_size:
        return [0]
    return list(range(0, n_rows, group_size))

def _dedupe_batch(df: pd.DataFrame) -> pd.DataFrame:
    """Latest wins within the current batch for (product_id, date, variation)."""
    if df.empty:
        return df
    return (df.sort_values(["product_id","date","variation","scraped_at"])
              .drop_duplicates(["product_id","date","variation"], keep="last"))

def _append_product_file(parquet_path: str, df_batch: pd.DataFrame, group_size: int = 50000) -> None:
    """
    Append a whole batch for one product, no full-file read. ZSTD for size.
    """
    if df_batch.empty:
        return
    path = Path(parquet_path)
    offsets = _row_group_offsets(len(df_batch), group_size)

    write(
        str(path),
        df_batch,
        compression="zstd",
        object_encoding="utf8",          # categoricals still dictionary-encoded
        append=path.exists(),
        file_scheme="simple",            # single file per product
        row_group_offsets=offsets,       # <-- correct fastparquet option
        stats=True
    )

import logging
# --- main: scan a directory of JSON dumps, write info.json + append parquet per product ---

async def get_total_items_in_json(path_to_json: str) -> int:
    with open(path_to_json, "r", encoding="utf-8") as f:
        parser = ijson.parse(f)
        for prefix, event, value in parser:
            if (prefix, event) == ('items', 'start_array'):
                count = 0
                for _ in parser:
                    count += 1
                    if (prefix, event) == ('items', 'end_array'):
                        break
                return count
    return 0

MAX_ROWS_PER_PRODUCT_BEFORE_FLUSH = 100_000   # flush when a single product buffer exceeds this
ROW_GROUP_TARGET = 50_000                    # used inside _append_product_file
from collections import defaultdict

async def process_json_dir_to_parquet(market_repository, path_to_json: str, market_code: str, output_path: str):
    """
    - Reads all *.json in `path_to_json`
    - Streams items with ijson (low RAM)
    - Batches per product_id across files
    - Periodically flushes big product buffers to parquet (single file per product)
    - Writes/keeps info.json per product
    """
    market_id = await get_market_id(market_repository, market_code)
    if market_id == -1:
        raise ValueError(f"Market ID not found for market code: {market_code}")

    os.makedirs(output_path, exist_ok=True)

    json_files = glob.glob(os.path.join(path_to_json, "*.json"))
    total_files_size = sum(os.path.getsize(f) for f in json_files)
    tqdm.write(f"Processing {len(json_files)} JSON files from {path_to_json}, total {total_files_size / (1024*1024):.2f} MB")

    # accumulate DataFrame chunks per product_id
    buffers: dict[int, list[pd.DataFrame]] = defaultdict(list)
    buffered_rows_count: dict[int, int] = defaultdict(int)

    def _flush_product(pid: int):
        """Flush one product buffer to parquet; clear its buffers."""
        frames = buffers.get(pid, [])
        if not frames:
            return
        df_batch = pd.concat(frames, ignore_index=True)
        df_batch = _dedupe_batch(df_batch)  # latest per (product_id, date, variation) within THIS run
        prod_dir = os.path.join(output_path, str(pid))
        os.makedirs(prod_dir, exist_ok=True)
        parquet_file_path = os.path.join(prod_dir, "data.parquet")
        _append_product_file(parquet_file_path, df_batch, group_size=ROW_GROUP_TARGET)
        buffers[pid].clear()
        buffered_rows_count[pid] = 0

    for json_file in tqdm(json_files, desc="Files", unit="file", dynamic_ncols=True):
        file_size_mb = os.path.getsize(json_file) / (1024 * 1024)
        tqdm.write(f"→ {os.path.basename(json_file)} ({file_size_mb:.2f} MB)")

        total_items = await get_total_items_in_json(json_file)
        if total_items == 0:
            tqdm.write(f"   (no items) {os.path.basename(json_file)}")
            continue

        with open(json_file, "rb") as f:  # IMPORTANT: pass a file object to ijson
            pbar = tqdm(total=total_items, desc=f"Items in {os.path.basename(json_file)}", unit="it", leave=False)
            try:
                for item in ijson.items(f, "items.item"):  # adjust prefix if your JSON structure differs
                    pbar.update(1)
                    if not isinstance(item, dict):
                        continue

                    pid = int(item["id"])
                    df_item = _df_from_item(item)
                    if df_item.empty:
                        continue

                    # buffer
                    buffers[pid].append(df_item)
                    buffered_rows_count[pid] += len(df_item)

                    # write/update info.json if missing (cheap)
                    prod_dir = os.path.join(output_path, str(pid))
                    os.makedirs(prod_dir, exist_ok=True)
                    info_fp = os.path.join(prod_dir, "info.json")
                    if not os.path.exists(info_fp):
                        with open(info_fp, "w", encoding="utf-8") as w:
                            json.dump({
                                "product_id": pid,
                                "shop_id": market_id,
                                "title": item.get("title"),
                                "vendor": item.get("vendor"),
                                "product_type": item.get("product_type"),
                                "tags": item.get("tags"),
                                "published_at": str(item.get("published_at")),
                                "created_at": str(item.get("created_at")),
                                "updated_at": str(item.get("updated_at")),
                            }, w, ensure_ascii=False, indent=2)

                    # flush if a single product buffer gets large (keeps RAM steady)
                    if buffered_rows_count[pid] >= MAX_ROWS_PER_PRODUCT_BEFORE_FLUSH:
                        _flush_product(pid)

            finally:
                pbar.close()

        tqdm.write(f"✓ Completed {os.path.basename(json_file)}")

    # final flush for all remaining products
    for pid in list(buffers.keys()):
        _flush_product(pid)

import pyarrow.parquet as pq
import tempfile
#add the foolowing code to add the data to a staging table
async def stage_data_from_parquet(product_repository: ProductRepository, parquet_base_path: str, batch_size: int = 10000):
    """
    Scan the parquet_base_path for product subdirectories, read their data.parquet files,
    and stage the data into the database using the provided repository.
    """
    product_dirs = [d for d in glob.glob(os.path.join(parquet_base_path, "*")) if os.path.isdir(d)]

    source = parquet_base_path.split("/")[-1]
    total_products = len(product_dirs)
    if total_products == 0:
        logging.warning(f"No product directories found in {parquet_base_path}")
        return

    


    parquet_files = []
    for prod_dir in product_dirs:
        parquet_file_path = os.path.join(prod_dir, "data.parquet")
        if os.path.exists(parquet_file_path):
            parquet_files.append(parquet_file_path)
        else:
            logging.warning(f"  (no data.parquet) {prod_dir}")
    
    if not parquet_files:
        logging.warning("No parquet files found to process")
        return
    
    logging.info(f"Staging data from {total_products} products in {parquet_base_path}")

    schema = pq.ParquetFile(parquet_files[0]).schema_arrow
    
    # Create temporary file for concatenated data
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as temp_file:
        temp_parquet_path = temp_file.name
    try:
        # Step 1: Concatenate all parquet files into one
        logging.info("Concatenating parquet files...")
        with pq.ParquetWriter(temp_parquet_path, schema=schema) as writer:
            for parquet_file_path in tqdm(parquet_files, desc="Concatenating files", unit="file", dynamic_ncols=True):
                try:
                    table = pq.read_table(parquet_file_path, schema=schema)
                    writer.write_table(table)
                except Exception as e:
                    logging.error(f"Error processing {parquet_file_path}: {e}")
                    continue
        
        # Step 2: Read the concatenated file and prepare for COPY
        logging.info("Reading concatenated data for staging...")
        combined_table = pq.read_table(temp_parquet_path)
        df = combined_table.to_pandas()
        
        total_rows = len(df)
        if total_rows == 0:
            logging.warning("No data found to stage")
            return

        logging.info(f"Total rows to stage: {total_rows}")

        # Step 3: Process in batches using COPY
        total_batches = (total_rows + batch_size - 1) // batch_size
        
        with tqdm(total=total_batches, desc="Staging to PostgreSQL", unit="batch") as pbar:
            for i in range(0, total_rows, batch_size):
                end_idx = min(i + batch_size, total_rows)
                batch_df = df.iloc[i:end_idx]
        

                try:
                    await product_repository.bulk_copy_prices(batch_df)
                    pbar.update(1)
                    pbar.set_postfix_str(f"Rows {i+1}-{end_idx}")
                except Exception as e:
                    logging.error(f"Error inserting batch {i//batch_size + 1}: {e}")
                    raise

        logging.info(f"✅ Staging completed successfully! Processed {total_rows} rows in {total_batches} batches.")

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_parquet_path)
        except Exception as e:
            print(f"Warning: Could not delete temporary file {temp_parquet_path}: {e}")