import glob
import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pandas as pd

from automana.core.repositories.app_integration.shopify.ApiShopify_repository import ShopifyAPIRepository
from automana.core.repositories.app_integration.shopify.market_repository import MarketRepository
from automana.core.repositories.app_integration.shopify.pipeline_repository import (
    ShopifyPipelineRepository,
    _map_variation,
)
from automana.core.repositories.app_integration.shopify.product_repository import ProductRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.ops.pipeline_services import track_step

logger = logging.getLogger(__name__)

_SHOPIFY_DATA_ROOT = os.getenv("SHOPIFY_DATA_ROOT", "/data/automana_data/shopify")


def _price_to_cents(price) -> Optional[int]:
    if price is None:
        return None
    return int((Decimal(str(price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _build_obs_dataframe(
    staging_rows: list[dict],
    tcg_to_cv: dict[int, str],
    cv_to_sp: dict[str, int],
    refs: dict,
) -> pd.DataFrame:
    """Convert staging rows to DataFrame ready for COPY into pricing.price_observation."""
    rows = []
    for r in staging_rows:
        tcg_id = r.get("tcg_id")
        if tcg_id is None:
            continue
        card_version_id = tcg_to_cv.get(int(tcg_id))
        if card_version_id is None:
            continue
        source_product_id = cv_to_sp.get(card_version_id)
        if source_product_id is None:
            continue

        condition_code, finish_code = _map_variation(r["variation"] or "Near Mint")
        condition_id = refs["conditions"].get(condition_code)
        finish_id = refs["finishes"].get(finish_code)
        if condition_id is None or finish_id is None:
            continue

        rows.append({
            "ts_date": str(r["date"])[:10],
            "price_type_id": refs["sell_type_id"],
            "finish_id": finish_id,
            "condition_id": condition_id,
            "language_id": refs["language_id"],
            "list_low_cents": None,
            "list_avg_cents": _price_to_cents(r["price"]),
            "sold_avg_cents": None,
            "list_count": None,
            "sold_count": None,
            "source_product_id": source_product_id,
            "data_provider_id": refs["data_provider_id"],
            "scraped_at": str(r["scraped_at"]),
        })

    _COLS = [
        "ts_date", "price_type_id", "finish_id", "condition_id", "language_id",
        "list_low_cents", "list_avg_cents", "sold_avg_cents", "list_count",
        "sold_count", "source_product_id", "data_provider_id", "scraped_at",
    ]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=_COLS)


@ServiceRegistry.register(
    path="shopify.pipeline.fetch_all_markets",
    db_repositories=["shopify_pipeline", "ops"],
    api_repositories=["shopify_api"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def fetch_all_markets(
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    shopify_api_repository: ShopifyAPIRepository,
    ingestion_run_id: int = None,
):
    markets = await shopify_pipeline_repository.get_active_pipeline_markets()
    logger.info("shopify_fetch: found active markets", extra={"count": len(markets)})
    market_dirs = {}
    for market in markets:
        market_id = market["market_id"]
        source_id = market["source_id"]
        api_url = market["api_url"]
        async with track_step(ops_repository, ingestion_run_id, f"fetch_storefront_{market_id}"):
            out_dir, pages = await shopify_api_repository.fetch_products_pages(
                api_url, source_id, _SHOPIFY_DATA_ROOT
            )
            logger.info(
                "shopify_fetch: fetched pages",
                extra={"market_id": market_id, "source_id": source_id, "pages": pages},
            )
            market_dirs[market_id] = out_dir
    return {"market_dirs": market_dirs, "markets": markets}


@ServiceRegistry.register(
    path="shopify.pipeline.process_to_parquet",
    db_repositories=["market", "shopify_pipeline", "ops"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def process_to_parquet(
    market_repository: MarketRepository,
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    market_dirs: dict = None,
    markets: list = None,
):
    parquet_dirs = {}
    for market in (markets or []):
        market_id = market["market_id"]
        source_code = market.get("source_code")
        parquet_dir = os.path.join(_SHOPIFY_DATA_ROOT, "parquet", str(market_id))

        async with track_step(ops_repository, ingestion_run_id, f"process_to_parquet_{market_id}"):
            from automana.core.services.app_integration.shopify.data_staging_service import (
                process_json_dir_to_parquet,
            )
            await process_json_dir_to_parquet(
                market_repository=market_repository,
                path_to_json=_SHOPIFY_DATA_ROOT,
                market_code=source_code,
                output_path=parquet_dir,
            )
            info_files = glob.glob(os.path.join(parquet_dir, "*", "info.json"))
            handle_rows = []
            for info_path in info_files:
                with open(info_path) as f:
                    info = json.load(f)
                handle_rows.append({
                    "product_id": str(info["product_id"]),
                    "market_id": market_id,
                    "handle": info.get("handle"),
                    "title": info.get("title"),
                })
            if handle_rows:
                await shopify_pipeline_repository.upsert_product_handles(handle_rows)

            parquet_dirs[market_id] = parquet_dir
    return {"parquet_dirs": parquet_dirs, "markets": markets}


@ServiceRegistry.register(
    path="shopify.pipeline.stage_raw",
    db_repositories=["product", "shopify_pipeline", "ops"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def stage_raw(
    product_repository: ProductRepository,
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    parquet_dirs: dict = None,
    markets: list = None,
):
    for market in (markets or []):
        market_id = market["market_id"]
        source_id = market["source_id"]
        parquet_dir = (parquet_dirs or {}).get(
            market_id,
            os.path.join(_SHOPIFY_DATA_ROOT, "parquet", str(market_id)),
        )
        async with track_step(ops_repository, ingestion_run_id, f"stage_raw_{market_id}"):
            from automana.core.services.app_integration.shopify.data_staging_service import (
                stage_data_from_parquet,
            )
            await stage_data_from_parquet(
                product_repository=product_repository,
                parquet_base_path=parquet_dir,
            )
            await shopify_pipeline_repository.connection.execute(
                """
                UPDATE pricing.shopify_staging_raw ssr
                SET source_id = $1
                FROM markets.product_ref mpr
                WHERE mpr.product_id = ssr.product_id::TEXT
                  AND mpr.market_id = $2
                  AND ssr.source_id IS NULL
                """,
                source_id,
                market_id,
            )
    return {"markets": markets}


@ServiceRegistry.register(
    path="shopify.pipeline.promote_observations",
    db_repositories=["shopify_pipeline", "ops"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def promote_observations(
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    markets: list = None,
):
    async with track_step(ops_repository, ingestion_run_id, "promote_observations"):
        staging_rows = await shopify_pipeline_repository.get_staging_rows()
        if not staging_rows:
            logger.info("shopify_promote: no staged rows found")
            return {}

        refs = await shopify_pipeline_repository.get_reference_ids()

        tcg_ids = list({int(r["tcg_id"]) for r in staging_rows if r.get("tcg_id")})
        tcg_to_cv = await shopify_pipeline_repository.find_card_versions_by_tcg_ids(tcg_ids)

        cv_to_sp: dict[str, int] = {}
        source_ids = list({r["source_id"] for r in staging_rows if r.get("source_id")})
        for source_id in source_ids:
            relevant_tcg_ids = [
                int(r["tcg_id"]) for r in staging_rows
                if r.get("tcg_id") and r.get("source_id") == source_id
            ]
            cv_ids = list({tcg_to_cv[t] for t in relevant_tcg_ids if t in tcg_to_cv})
            mapping = await shopify_pipeline_repository.bootstrap_source_products(cv_ids, source_id)
            cv_to_sp.update(mapping)

        df = _build_obs_dataframe(staging_rows, tcg_to_cv, cv_to_sp, refs)
        inserted = await shopify_pipeline_repository.bulk_copy_observations(df)
        await shopify_pipeline_repository.truncate_staging()

        logger.info(
            "shopify_promote: complete",
            extra={"staged_rows": len(staging_rows), "inserted": inserted},
        )
        return {"inserted": inserted}
