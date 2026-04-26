import os, json,  logging
import pandas as pd
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository
import time
from automana.core.service_registry import ServiceRegistry
from tqdm import tqdm
from automana.core.models.pipelines.mtg_stock import MTGStockBatchStep
from automana.core.repositories.ops.ops_repository import OpsRepository

logger = logging.getLogger(__name__)

async def process_info_file(path):
    with open(path, "r") as f:
        obj = json.load(f)
        card_set = obj.get("card_set", None)
    return {
        "mtgstock": obj["id"],
        "card_name": obj.get("name", None),
        "set_abbr": card_set.get("abbreviation", None) if card_set else None,
        "collector_number": obj.get("collector_number", None),
        "cardtrader": obj.get("cardtrader", None),
        "scryfallId": obj.get("scryfallId", None),
        "multiverse_ids": obj.get("multiverse_ids", None),
        "tcg_id": obj.get("tcg_id", None),
        "cardtrader_id": obj.get("cardtrader_id", None),
            # adjust key
    }

async def process_prices_file(path, id_dict):

    df = pd.read_parquet(path)
    # asyncpg.copy_to_table(..., header=True) maps by column NAME, so the
    # DataFrame columns must match pricing.raw_mtg_stock_price exactly.
    # The parquet file writes a `date` column; the DB column is `ts_date`.
    df = df.rename(columns={"date": "ts_date"})
    df["print_id"] = id_dict.get("mtgstock", None)
    df['game_code'] =  "mtg"
    df['source_code'] = 'mtgstocks'
    df['scraped_at'] = pd.Timestamp.now()
    return df[["ts_date"
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
    runs_in_transaction=False,
    command_timeout=3600,
)
async def bulk_load(price_repository: PriceRepository
                    , ops_repository: OpsRepository
                    , root_folder
                    , batch_size=10000
                    , ingestion_run_id: int = None
                    , market: str = "tcg"):
    """TODO: include scryfall_id, card_name, set_abbr, collector_number in the
    staging table to simplify dim/fact loads and avoid re-calling Scryfall API
    in the dimension load step."""
    step_name = "bulk_load"
    price_rows = []
    batch_start = 0
    batch_end = 0
    batch_number = 1
    folder_errors = 0
    ids_master_dict = {}
    # Cache listdir once — the directory can hold ~500k entries on a full load.
    folders = os.listdir(root_folder)
    try:
        if ingestion_run_id is not None:
            await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="running")
        deleted = await price_repository.clear_raw_prices()
        logger.info("bulk_load: cleared %d stale rows from raw_mtg_stock_price", deleted)
        for i, folder in tqdm(enumerate(folders, 1), desc="Processing MTG Stock folders", total=len(folders)):

            try:

                batch_end +=1
                pdir = os.path.join(root_folder,folder)
                info_path = os.path.join(pdir, "info.json")
                # Writer in data_loader.py uses `prices.{market}.parquet`; mirror it here.
                price_path = os.path.join(pdir, f"prices.{market}.parquet")
                id_dict = await process_info_file(info_path)
                ids_master_dict[id_dict["mtgstock"]] = {k: v for k, v in id_dict.items() if k != "mtgstock"}
                price_df = await process_prices_file(price_path, id_dict)
                price_df["card_name"] = id_dict.get("card_name", None)
                price_df["set_abbr"] = id_dict.get("set_abbr", None)
                price_df["collector_number"] = id_dict.get("collector_number", None)
                price_df["scryfall_id"] = id_dict.get("scryfallId", None)
                price_df["tcg_id"] = id_dict.get("tcg_id", None)
                price_df["cardtrader_id"] = id_dict.get("cardtrader_id", None)
                price_rows.append(price_df)
            except Exception as e:
                folder_errors += 1
                logger.warning(f"Error processing folder: {folder} Error: {e}")
            if i % batch_size == 0 and price_rows:
                big_price_df = pd.concat(price_rows, ignore_index=True)
                start = time.perf_counter()
                if ingestion_run_id is not None:
                    await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="running")
                await price_repository.copy_prices_mtgstock(big_price_df)
                if ingestion_run_id is not None:
                    await ops_repository.update_ids_master_dict(ingestion_run_id=ingestion_run_id, ids_master_dict=ids_master_dict)
                ids_master_dict = {}
                batch_start = batch_end
                elapsed = time.perf_counter() - start

                batch_result = MTGStockBatchStep(
                    ingestion_run_id=ingestion_run_id,
                    step_name=step_name,
                    batch_seq=batch_number,
                    range_start=batch_start,
                    range_end=batch_end,
                    total_in_batch=len(big_price_df),
                    items_ok=len(big_price_df),
                    items_failed=folder_errors,
                    status="success" if folder_errors == 0 else "partial",
                    bytes_processed=int(big_price_df.memory_usage(deep=True).sum()),
                    duration_ms=int(elapsed * 1000),
                )
                await ops_repository.insert_batch_step(batch_result)
                batch_number += 1
                folder_errors = 0
                logger.info("copy_prices took %.3f s for %d rows", elapsed, len(big_price_df))
                price_rows.clear()
        # Leftover tail — flush anything remaining and record the final batch
        # step so the ops audit reflects the full load.
        if price_rows:
            big_price_df = pd.concat(price_rows, ignore_index=True)
            start = time.perf_counter()
            await price_repository.copy_prices_mtgstock(big_price_df)
            if ingestion_run_id is not None:
                await ops_repository.update_ids_master_dict(ingestion_run_id=ingestion_run_id, ids_master_dict=ids_master_dict)
                elapsed = time.perf_counter() - start
                await ops_repository.insert_batch_step(MTGStockBatchStep(
                    ingestion_run_id=ingestion_run_id,
                    step_name=step_name,
                    batch_seq=batch_number,
                    range_start=batch_start,
                    range_end=batch_end,
                    total_in_batch=len(big_price_df),
                    items_ok=len(big_price_df),
                    items_failed=folder_errors,
                    status="success" if folder_errors == 0 else "partial",
                    bytes_processed=int(big_price_df.memory_usage(deep=True).sum()),
                    duration_ms=int(elapsed * 1000),
                ))
            ids_master_dict.clear()
    
    except Exception as e:
        if ingestion_run_id is not None:
            await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="failed", error_details={"error": str(e)})
        raise e
    if ingestion_run_id is not None:
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id,current_step=step_name ,status="success")

@ServiceRegistry.register(
    path="mtg_stock.data_staging.from_raw_to_staging",
    db_repositories = ["price", "ops"],
    # pricing.load_staging_prices_batched issues per-batch COMMIT/ROLLBACK.
    # Postgres forbids internal transaction control inside a CALL block, so
    # the service must run on a non-atomic connection.
    runs_in_transaction=False,
    command_timeout=86400,  # 24h — 456M raw rows across 14 years; generous ceiling
)
async def from_raw_to_staging(price_repository: PriceRepository
                              , ops_repository: OpsRepository
                              , ingestion_run_id: int
                              , source_name: str = "mtgstocks"):
    """Pivot raw wide rows into narrow stg_price_observation rows, resolving
    card_version_id via mtgstock_id → external ids → set+collector.
    `source_name` must match a `pricing.price_source.code` value."""
    step_name = "raw_to_staging"
    if ingestion_run_id is not None:
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id, current_step=step_name, status="running")
    try:
        await price_repository.call_load_stage_from_raw(source_name=source_name, ingestion_run_id=ingestion_run_id)
        if ingestion_run_id is not None:
            await ops_repository.update_run(ingestion_run_id=ingestion_run_id, current_step=step_name, status="success")
    except Exception as e:
        if ingestion_run_id is not None:
            await ops_repository.update_run(ingestion_run_id=ingestion_run_id, current_step=step_name, status="failed", error_details={"error": str(e)})
        raise e

@ServiceRegistry.register(
    path="mtg_stock.data_staging.retry_rejects",
    db_repositories = ["price", "ops"],
    # pricing.resolve_price_rejects is a plain FUNCTION (no internal COMMIT/
    # ROLLBACK), but we still need `runs_in_transaction=False` so the `failed`
    # status update in the except block auto-commits independently — under
    # the atomic wrapper the re-raise would roll that status update back and
    # leave the ops audit blank. Same reasoning as the siblings above.
    runs_in_transaction=False,
    command_timeout=3600,
)
async def retry_rejects(price_repository: PriceRepository,
                        ops_repository: OpsRepository,
                        ingestion_run_id: int,
                        limit: int = 50000,
                        only_unresolved: bool = True):
    """Re-feed rows from stg_price_observation_reject back into staging via
    pricing.resolve_price_rejects(). Runs between from_raw_to_staging and
    from_staging_to_prices so that rejects resolved via the new scryfall
    migration rows / identifier updates can still make it into the current
    day's price_observation promotion."""
    step_name = "retry_rejects"
    if ingestion_run_id is not None:
        await ops_repository.update_run(
            ingestion_run_id=ingestion_run_id, current_step=step_name, status="running"
        )
    try:
        logger.info(
            "retry_rejects: starting limit=%d only_unresolved=%s ingestion_run_id=%s",
            limit, only_unresolved, ingestion_run_id,
        )
        rows = await price_repository.call_resolve_price_rejects(
            limit=limit, only_unresolved=only_unresolved
        )
        logger.info(
            "retry_rejects: resolved %d reject rows (limit=%d only_unresolved=%s)",
            rows, limit, only_unresolved,
        )
        if ingestion_run_id is not None:
            await ops_repository.update_run(
                ingestion_run_id=ingestion_run_id, current_step=step_name, status="success",
                notes=f"Resolved {rows} reject rows",
            )
        return {"rows_resolved": rows}
    except Exception as e:
        if ingestion_run_id is not None:
            await ops_repository.update_run(
                ingestion_run_id=ingestion_run_id, current_step=step_name, status="failed",
                error_details={"error": str(e)},
            )
        logger.exception("retry_rejects: failed with %s", e)
        raise


@ServiceRegistry.register(
    path="mtg_stock.data_staging.from_staging_to_prices",
    db_repositories = ["price", "ops"],
    # pricing.load_prices_from_staged_batched issues per-batch COMMIT. Same
    # reason as from_raw_to_staging above — must run outside an atomic block.
    runs_in_transaction=False,
    command_timeout=3600,
)
async def from_staging_to_prices(price_repository: PriceRepository
                                 , ops_repository: OpsRepository
                                 , ingestion_run_id: int):
    """Promote stg_price_observation rows into the pricing.price_observation
    hypertable via pricing.load_prices_from_staged_batched(). The previously
    separate `from_staging_to_dim` step has been removed — no
    `load_dim_from_staging` procedure exists in the DB."""
    step_name = "staging_to_prices"
    if ingestion_run_id is not None:
        await ops_repository.update_run(ingestion_run_id=ingestion_run_id, current_step=step_name, status="running")
    try:
        await price_repository.call_load_prices_from_staging()
        if ingestion_run_id is not None:
            await ops_repository.update_run(ingestion_run_id=ingestion_run_id, current_step=step_name, status="success")
    except Exception as e:
        if ingestion_run_id is not None:
            await ops_repository.update_run(ingestion_run_id=ingestion_run_id, current_step=step_name, status="failed", error_details={"error": str(e)})
        raise e

