import asyncio, httpx, hashlib, json
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import pyarrow as pa, pyarrow.parquet as pq
import logging

from traitlets import List
from backend.repositories.app_integration.mtg_stock.ApiMtgStock_repository import ApiMtgStockRepository

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

BASE = Path(__file__).resolve().parents[4] / "data/mtgstocks/raw/prints"
   # concurrency guard
def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
#service

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

async def run_batch(mtg_stock_repository : ApiMtgStockRepository
                    , print_ids : Optional[List[int]]
                    , range_start: Optional[int]
                    , range_end: Optional[int]
                    , batch_size: Optional[int]=10):
    #try:
    async with mtg_stock_repository as repo:
        inputs = print_ids if print_ids is not None else list(range(range_start, range_end + 1))
        counter = 0
        while counter < len(inputs):
            end = counter + batch_size
            batch = inputs[counter:min(end, len(inputs))]
            results = await repo.fetch_card_data_batches(batch)
            if results is None or len(results) == 0:
                logger.warning("No results fetched from MTG Stock API")
                return []
            for result in results:
                if not result or 'error' in result:
                    logger.warning(f"Error in result: {result}")
                    continue
                pid = str(result.get('card_id'))
                if not pid:
                    logger.warning(f"Missing card_id in result: {result}")
                    continue
                pdir = BASE / pid
                pdir.mkdir(parents=True, exist_ok=True)
                info_path = pdir / "info.json"
                info_path.write_bytes(result.get('details'))
                info_hash = _hash_bytes(result.get('details'))

                price_path = pdir  / "prices.parquet"
                price_path.write_bytes(result.get('prices'))
                prices_to_parquet(result.get('card_id'), result.get('prices'), price_path)
                prices_hash = _hash_bytes(result.get('prices'))
                # Process each detail as needed
            counter += batch_size
        #deal with leftov
      
    return {
        "print_id": result.get('card_id'),
        "info_path": str(info_path),
        "prices_path": str(price_path),
        "info_hash": info_hash,
        "prices_hash": prices_hash,
        "info_fetched_at": datetime.now(timezone.utc).isoformat(),
        "prices_fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok"
    }


