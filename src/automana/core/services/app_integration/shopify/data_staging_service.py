import glob
import ijson
import json
import logging
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq
from bs4 import BeautifulSoup

from automana.core.models.shopify import shopify_theme
from automana.core.repositories.app_integration.shopify.market_repository import MarketRepository
from automana.core.repositories.app_integration.shopify.product_repository import ProductRepository
from automana.core.framework.registry import ServiceRegistry
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)


async def get_market_id(market_repository, code: str) -> int:
    try:
        market_id = await market_repository.get_market_code(code)
        if market_id is not None:
            return market_id
        return -1
    except Exception as e:
        logger.warning("market_id_fetch_failed", extra={"code": code, "error": str(e)})
        return -1


AUS_TZ = ZoneInfo("Australia/Brisbane")


def _to_utc(x):
    if x is None or x == "":
        return pd.NaT
    return pd.to_datetime(x, utc=True, errors="coerce")


def _current_local_date():
    return pd.Timestamp(datetime.now(AUS_TZ).date())


def _df_from_item(item: dict) -> pd.DataFrame:
    variants = item.get("variants", []) or []
    if not variants:
        return pd.DataFrame(columns=["product_id", "date", "price", "variation", "scraped_at"])

    rows = []
    for v in variants:
        rows.append({
            "product_id": item.get("id"),
            "date": _to_utc(v.get("updated_at")),
            "variation": v.get("title"),
            "price": float(v["price"]) if v.get("price") is not None else None,
            "scraped_at": _current_local_date(),
        })

    df = pd.DataFrame(rows, columns=["product_id", "date", "variation", "price", "scraped_at"])
    df["product_id"] = df["product_id"].astype("int64")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], utc=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").astype("float64")
    df["variation"] = df["variation"].astype("category")
    return df[["product_id", "date", "variation", "price", "scraped_at"]]


def _row_group_offsets(n_rows: int, group_size: int) -> list[int]:
    if group_size <= 0 or n_rows <= group_size:
        return [0]
    return list(range(0, n_rows, group_size))


def _dedupe_batch(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return (
        df.sort_values(["product_id", "date", "variation", "scraped_at"])
        .drop_duplicates(["product_id", "date", "variation"], keep="last")
    )


def _append_product_file(parquet_path: str, df_batch: pd.DataFrame, group_size: int = 50000) -> None:
    if df_batch.empty:
        return
    from fastparquet import write  # optional dep — not installed in API process
    path = Path(parquet_path)
    offsets = _row_group_offsets(len(df_batch), group_size)
    write(
        str(path),
        df_batch,
        compression="zstd",
        object_encoding="utf8",
        append=path.exists(),
        file_scheme="simple",
        row_group_offsets=offsets,
        stats=True,
    )


async def get_total_items_in_json(path_to_json: str) -> int:
    with open(path_to_json, "r", encoding="utf-8") as f:
        parser = ijson.parse(f)
        for prefix, event, value in parser:
            if (prefix, event) == ("items", "start_array"):
                count = 0
                for _ in parser:
                    count += 1
                    if (prefix, event) == ("items", "end_array"):
                        break
                return count
    return 0


MAX_ROWS_PER_PRODUCT_BEFORE_FLUSH = 100_000
ROW_GROUP_TARGET = 50_000


async def parse_html_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


async def get_card_id_from_html(html: str) -> Optional[str]:
    if not html:
        return None
    try:
        soup = BeautifulSoup(html, "html.parser")
        catalog_div = soup.find("div", class_="catalogMetaData")
        if catalog_div:
            return catalog_div.get("data-cardid")
        return None
    except Exception as e:
        logger.warning("card_id_extraction_failed", extra={"error": str(e)})
        return None


async def extract_all_metadata_from_html(html: str) -> Dict[str, Optional[str]]:
    if not html:
        return {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        catalog_div = soup.find("div", class_="catalogMetaData")
        if catalog_div:
            return {
                "card_id": catalog_div.get("data-cardid"),
                "tcg_id": catalog_div.get("data-tcgid"),
                "card_type": catalog_div.get("data-cardtype"),
                "last_updated": catalog_div.get("data-lastupdated"),
            }
        return {}
    except Exception as e:
        logger.warning("metadata_extraction_failed", extra={"error": str(e)})
        return {}


@ServiceRegistry.register(
    path="shopify.data.process_to_parquet",
    db_repositories=["market"],
    storage_services=["shopify"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def process_json_dir_to_parquet(
    market_repository: MarketRepository,
    storage_service: StorageService,
    path_to_json: str,
    market_code: str,
    output_path: str,
):
    market_id = await get_market_id(market_repository, market_code)
    if market_id == -1:
        raise ValueError(f"Market ID not found for market code: {market_code}")

    storage_base = storage_service.backend.base_path
    json_files = sorted(storage_base.glob(f"{market_id}_*/**/*products.json"))
    total_files = len(json_files)
    total_files_size = sum(f.stat().st_size for f in json_files)
    logger.info(
        "parquet_process_start",
        extra={"file_count": total_files, "total_mb": round(total_files_size / (1024 * 1024), 2)},
    )

    # Derive the parquet output directory relative to the storage root
    try:
        rel_output = str(Path(output_path).relative_to(storage_base))
    except ValueError:
        rel_output = f"parquet/{market_id}"

    buffers: dict[int, list[pd.DataFrame]] = defaultdict(list)
    buffered_rows_count: dict[int, int] = defaultdict(int)

    def _flush_product(pid: int):
        frames = buffers.get(pid, [])
        if not frames:
            return
        df_batch = pd.concat(frames, ignore_index=True)
        df_batch = _dedupe_batch(df_batch)
        # fastparquet requires a filesystem path; resolve_path bridges the storage abstraction
        parquet_path = storage_service.backend.resolve_path(f"{rel_output}/{pid}/data.parquet")
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        _append_product_file(str(parquet_path), df_batch, group_size=ROW_GROUP_TARGET)
        buffers[pid].clear()
        buffered_rows_count[pid] = 0

    for file_index, json_file in enumerate(json_files, 1):
        file_size_mb = json_file.stat().st_size / (1024 * 1024)
        logger.info(
            "parquet_process_file_start",
            extra={
                "file": json_file.name,
                "file_size_mb": round(file_size_mb, 2),
                "file_index": file_index,
                "total_files": total_files,
            },
        )

        total_items = await get_total_items_in_json(str(json_file))
        if total_items == 0:
            logger.info("parquet_process_file_empty", extra={"file": json_file.name})
            continue

        items_processed = 0
        with open(json_file, "rb") as f:
            try:
                for item in ijson.items(f, "items.item"):
                    if not isinstance(item, dict):
                        continue

                    pid = int(item["id"])
                    df_item = _df_from_item(item)
                    if df_item.empty:
                        continue

                    meta_data = await extract_all_metadata_from_html(item.get("body_html", ""))
                    df_item["card_id"] = meta_data.get("card_id")
                    df_item["tcg_id"] = meta_data.get("tcg_id")
                    buffers[pid].append(df_item)
                    buffered_rows_count[pid] += len(df_item)

                    info_rel = f"{rel_output}/{pid}/info.json"
                    if not await storage_service.file_exists(info_rel):
                        await storage_service.save_json(info_rel, {
                            "product_id": pid,
                            "shop_id": market_id,
                            "title": item.get("title"),
                            "handle": item.get("handle"),
                            "vendor": item.get("vendor"),
                            "product_type": item.get("product_type"),
                            "card_id": meta_data.get("card_id"),
                            "tcg_id": meta_data.get("tcg_id"),
                            "card_type": meta_data.get("card_type"),
                            "tags": item.get("tags"),
                            "published_at": str(item.get("published_at")),
                            "created_at": str(item.get("created_at")),
                            "updated_at": str(item.get("updated_at")),
                        })

                    if buffered_rows_count[pid] >= MAX_ROWS_PER_PRODUCT_BEFORE_FLUSH:
                        _flush_product(pid)

                    items_processed += 1
                    if items_processed % 1000 == 0:
                        logger.info(
                            "parquet_process_progress",
                            extra={"file": json_file.name, "items_processed": items_processed, "total_items": total_items},
                        )
            except Exception as e:
                logger.error("parquet_file_processing_failed", extra={"file": str(json_file), "error": str(e)})

        logger.info("parquet_process_file_complete", extra={"file": json_file.name, "items_processed": items_processed})

    for pid in list(buffers.keys()):
        _flush_product(pid)

    logger.info("parquet_process_complete", extra={"total_files": total_files})


@ServiceRegistry.register(
    path="shopify.data.stage_from_parquet",
    db_repositories=["product"],
    storage_services=["shopify"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def stage_data_from_parquet(
    product_repository: ProductRepository,
    storage_service: StorageService,
    parquet_base_path: str,
    batch_size: int = 10000,
):
    storage_base = storage_service.backend.base_path
    try:
        rel_base = str(Path(parquet_base_path).relative_to(storage_base))
    except ValueError:
        rel_base = parquet_base_path

    base_dir = storage_service.backend.resolve_path(rel_base)
    product_dirs = [d for d in base_dir.iterdir() if d.is_dir()] if base_dir.exists() else []

    total_products = len(product_dirs)
    if total_products == 0:
        logger.warning("no_product_dirs", extra={"path": parquet_base_path})
        return

    parquet_files = []
    for prod_dir in product_dirs:
        parquet_file_path = prod_dir / "data.parquet"
        if parquet_file_path.exists():
            parquet_files.append(parquet_file_path)
        else:
            logger.warning("missing_parquet", extra={"dir": str(prod_dir)})

    if not parquet_files:
        logger.warning("no_parquet_files", extra={"path": parquet_base_path})
        return

    logger.info("staging_start", extra={"total_products": total_products, "path": parquet_base_path})

    schema = pq.ParquetFile(parquet_files[0]).schema_arrow

    # Temp merge file lives under the storage root so cleanup goes through storage
    tmp_rel = "_tmp/merge.parquet"
    temp_parquet_path = storage_service.backend.resolve_path(tmp_rel)
    temp_parquet_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("concatenating_parquet_files")
        with pq.ParquetWriter(str(temp_parquet_path), schema=schema) as writer:
            for i, parquet_file_path in enumerate(parquet_files, 1):
                logger.info(
                    "parquet_concat_file",
                    extra={"file_index": i, "total_files": len(parquet_files), "file": parquet_file_path.name},
                )
                try:
                    table = pq.read_table(parquet_file_path, schema=schema)
                    writer.write_table(table)
                except Exception as e:
                    logger.error("parquet_read_failed", extra={"file": str(parquet_file_path), "error": str(e)})

        logger.info("reading_concatenated_parquet")
        combined_table = pq.read_table(str(temp_parquet_path))
        df = combined_table.to_pandas()


        total_rows = len(df)
        if total_rows == 0:
            logger.warning("no_rows_to_stage")
            return

        logger.info("staging_rows", extra={"total_rows": total_rows})
        total_batches = (total_rows + batch_size - 1) // batch_size

        for batch_num, i in enumerate(range(0, total_rows, batch_size), 1):
            end_idx = min(i + batch_size, total_rows)
            batch_df = df.iloc[i:end_idx]
            logger.info(
                "staging_batch",
                extra={"batch": batch_num, "total_batches": total_batches, "rows_start": i + 1, "rows_end": end_idx},
            )
            try:
                await product_repository.bulk_copy_prices(batch_df)
            except Exception as e:
                logger.error("batch_insert_failed", extra={"batch": batch_num, "error": str(e)})
                raise

        logger.info("staging_complete", extra={"total_rows": total_rows, "total_batches": total_batches})

    finally:
        await storage_service.delete_file(tmp_rel)

