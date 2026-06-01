import asyncio
import logging
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import pandas as pd

from automana.core.repositories.app_integration.shopify.ApiShopify_repository import ShopifyAPIRepository
from automana.core.repositories.app_integration.shopify.collection_repository import ShopifyCollectionRepository
from automana.core.repositories.app_integration.shopify.market_repository import MarketRepository
from automana.core.repositories.app_integration.shopify.pipeline_repository import (
    ShopifyPipelineRepository,
    _map_variation,
)
from automana.core.repositories.app_integration.shopify.product_repository import ProductRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.framework.registry import ServiceRegistry
from automana.core.models.shopify.shopify_theme import InsertCollection
from automana.core.services.ops.pipeline_services import track_step
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)


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
    path="shopify.pipeline.fetch_collections",
    db_repositories=["shopify_pipeline", "collection", "ops"],
    api_repositories=["shopify_api"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def fetch_collections(
    shopify_pipeline_repository: ShopifyPipelineRepository,
    collection_repository: ShopifyCollectionRepository,
    ops_repository: OpsRepository,
    shopify_api_repository: ShopifyAPIRepository,
    ingestion_run_id: int = None,
) -> dict:
    """Discover all collection handles for every active market via the Shopify sitemap.

    Stores handles in markets.collection_handles with game_code=NULL (unclassified).
    Existing rows (already classified by operator) are untouched — add_many uses
    ON CONFLICT DO NOTHING so game_code marks survive weekly re-runs.

    Stores handles with game_code=NULL. classify_collections (next step) auto-classifies
    them by sampling products and checking for TCG IDs in the card catalog.
    """
    markets = await shopify_pipeline_repository.get_active_pipeline_markets()
    total_synced = 0

    for market in markets:
        market_id = market["market_id"]
        api_url = market["api_url"]

        async with track_step(ops_repository, ingestion_run_id, f"fetch_collections_{market_id}"):
            handles = await shopify_api_repository.get_sitemap_collection_handles(api_url)
            rows = [{"market_id": market_id, "name": h} for h in handles]

            if rows:
                insert_rows = [InsertCollection(market_id=r["market_id"], name=r["name"]) for r in rows]
                await collection_repository.add_many(insert_rows)

            total_synced += len(rows)
            logger.info(
                "shopify_collections: synced",
                extra={"market_id": market_id, "handles": len(handles)},
            )

    return {"collections_synced": total_synced}


@ServiceRegistry.register(
    path="shopify.pipeline.classify_collections",
    db_repositories=["shopify_pipeline", "ops"],
    api_repositories=["shopify_api"],
    runs_in_transaction=False,
    command_timeout=7200,
)
async def classify_collections(
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    shopify_api_repository: ShopifyAPIRepository,
    ingestion_run_id: int = None,
) -> dict:
    """Auto-classify unclassified collection handles by sampling products.

    For each handle with game_code=NULL, fetches the first 10 products and
    checks if any have a data-tcgid present in the card catalog.
    Sets game_code='mtg' on match, 'other' otherwise.
    Already-classified handles are skipped — manual overrides survive re-runs.
    """
    import re

    markets = await shopify_pipeline_repository.get_active_pipeline_markets()
    total_classified = 0

    for market in markets:
        market_id = market["market_id"]
        api_url = market["api_url"]

        handles = await shopify_pipeline_repository.get_unclassified_collection_handles(market_id)
        if not handles:
            logger.info("shopify_classify: all handles already classified", extra={"market_id": market_id})
            continue

        logger.info(
            "shopify_classify: classifying handles",
            extra={"market_id": market_id, "count": len(handles)},
        )

        async with track_step(ops_repository, ingestion_run_id, f"classify_collections_{market_id}"):
            sem = asyncio.Semaphore(5)
            classified_count = 0

            async def classify_one(handle: str) -> None:
                nonlocal classified_count
                async with sem:
                    products = await shopify_api_repository.get_collection_products_page(
                        api_url, handle, since_id=0, limit=10
                    )
                    tcg_ids = []
                    for p in products:
                        m = re.search(r'data-tcgid="(\d+)"', p.get("body_html", "") or "")
                        if m:
                            tcg_ids.append(int(m.group(1)))

                    is_mtg = bool(tcg_ids) and await shopify_pipeline_repository.fetch_any_tcg_id_matches(tcg_ids)
                    game_code = "mtg" if is_mtg else "other"

                    await shopify_pipeline_repository.update_collection_game_code(market_id, handle, game_code)
                    classified_count += 1

                    if is_mtg:
                        logger.info("shopify_classify: mtg", extra={"handle": handle})

            async with shopify_api_repository:
                await asyncio.gather(*[classify_one(h) for h in handles])

            total_classified += classified_count
            logger.info(
                "shopify_classify: market done",
                extra={"market_id": market_id, "classified": classified_count},
            )

    return {"collections_classified": total_classified}


@ServiceRegistry.register(
    path="shopify.pipeline.fetch_all_markets",
    db_repositories=["shopify_pipeline", "ops"],
    api_repositories=["shopify_api"],
    storage_services=["shopify"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def fetch_all_markets(
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    shopify_api_repository: ShopifyAPIRepository,
    storage_service: StorageService,
    ingestion_run_id: int = None,
):
    """Fetch products for every MTG-classified collection across all active markets.

    Uses since_id pagination (no page cap) and asyncio.gather with a semaphore
    for concurrent collection fetching within a market.

    First-run behaviour: if no collections are marked game_code='mtg' for a market,
    logs a warning and skips that market. Run fetch_collections first, then classify.
    """
    markets = await shopify_pipeline_repository.get_active_pipeline_markets()
    logger.info("shopify_fetch: found active markets", extra={"count": len(markets)})
    market_dirs = {}

    for market in markets:
        market_id = market["market_id"]
        source_id = market["source_id"]
        api_url = market["api_url"]

        handles = await shopify_pipeline_repository.get_mtg_collection_handles(market_id)
        if not handles:
            logger.warning(
                "shopify_fetch: no mtg collections, skipping market",
                extra={
                    "market_id": market_id,
                    "hint": "run fetch_collections then: UPDATE markets.collection_handles "
                            "SET game_code='mtg' WHERE market_id=<id> AND name IN (...)",
                },
            )
            continue

        async with track_step(ops_repository, ingestion_run_id, f"fetch_storefront_{market_id}"):
            sem = asyncio.Semaphore(5)
            pages_total = 0

            async def fetch_one(handle: str) -> None:
                nonlocal pages_total
                async with sem:
                    page = 0
                    since_id = 0
                    while True:
                        products = await shopify_api_repository.get_collection_products_page(
                            api_url, handle, since_id=since_id, limit=250
                        )
                        if not products:
                            break
                        await storage_service.save_json(
                            f"{source_id}_fetch/{handle}_page_{page}_products.json",
                            {"_collection_handle": handle, "items": products},
                        )
                        since_id = products[-1]["id"]
                        page += 1
                        pages_total += 1
                    logger.info(
                        "shopify_fetch: collection done",
                        extra={"market_id": market_id, "handle": handle, "pages": page},
                    )

            async with shopify_api_repository:
                await asyncio.gather(*[fetch_one(h) for h in handles])

            logger.info(
                "shopify_fetch: market done",
                extra={"market_id": market_id, "handles": len(handles), "pages": pages_total},
            )
            market_dirs[market_id] = str(
                storage_service.backend.resolve_path(f"{source_id}_fetch")
            )

    return {"market_dirs": market_dirs, "markets": markets}


@ServiceRegistry.register(
    path="shopify.pipeline.process_to_parquet",
    db_repositories=["market", "shopify_pipeline", "ops"],
    storage_services=["shopify"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def process_to_parquet(
    market_repository: MarketRepository,
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    storage_service: StorageService,
    ingestion_run_id: int = None,
    market_dirs: dict = None,
    markets: list = None,
):
    parquet_dirs = {}
    for market in (markets or []):
        market_id = market["market_id"]
        source_code = market.get("source_code")
        out_dir = (market_dirs or {}).get(market_id)
        if out_dir is None:
            logger.warning("shopify_process: no fetch dir for market", extra={"market_id": market_id})
            continue
        data_root = str(Path(out_dir).parent)
        parquet_dir = str(Path(data_root) / "parquet" / str(market_id))

        async with track_step(ops_repository, ingestion_run_id, f"process_to_parquet_{market_id}"):
            from automana.core.services.app_integration.shopify.data_staging_service import (
                process_json_dir_to_parquet,
            )
            await process_json_dir_to_parquet(
                market_repository=market_repository,
                storage_service=storage_service,
                path_to_json=data_root,
                market_code=source_code,
                output_path=parquet_dir,
            )
            # Read info.json files written by the staging service via the storage layer
            storage_base = storage_service.backend.base_path
            try:
                rel_parquet = str(Path(parquet_dir).relative_to(storage_base))
            except ValueError:
                rel_parquet = parquet_dir
            info_paths = sorted(storage_service.backend.resolve_path(rel_parquet).glob("*/info.json"))
            handle_rows = []
            for info_path in info_paths:
                rel_info = str(info_path.relative_to(storage_base))
                info = await storage_service.load_json(rel_info)
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
    storage_services=["shopify"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def stage_raw(
    product_repository: ProductRepository,
    shopify_pipeline_repository: ShopifyPipelineRepository,
    ops_repository: OpsRepository,
    storage_service: StorageService,
    ingestion_run_id: int = None,
    parquet_dirs: dict = None,
    markets: list = None,
):
    for market in (markets or []):
        market_id = market["market_id"]
        source_id = market["source_id"]
        parquet_dir = (parquet_dirs or {}).get(market_id)
        if parquet_dir is None:
            logger.warning("shopify_stage: no parquet dir for market", extra={"market_id": market_id})
            continue
        async with track_step(ops_repository, ingestion_run_id, f"stage_raw_{market_id}"):
            from automana.core.services.app_integration.shopify.data_staging_service import (
                stage_data_from_parquet,
            )
            await stage_data_from_parquet(
                product_repository=product_repository,
                storage_service=storage_service,
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
