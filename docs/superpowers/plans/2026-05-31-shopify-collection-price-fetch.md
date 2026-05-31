# Shopify Collection-Based Price Fetch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken `/products.json` fetcher with a sitemap-driven, collection-based, `since_id`-paginated pipeline that fully covers all MTG singles on `tcg.goodgames.com.au` and any future Shopify stores.

**Architecture:** `fetch_collections` discovers collection handles from the store sitemap and stores them unclassified; the operator marks MTG collections `game_code = 'mtg'`; `fetch_all_markets` concurrently fetches products per marked collection via `since_id` pagination; downstream steps (parquet → stage → promote) are unchanged except for in-stock vs per-set deduplication priority.

**Tech Stack:** Python asyncio, httpx, pandas, ijson, fastparquet, Celery chain, PostgreSQL asyncpg, Shopify public storefront REST API.

---

## File Map

| Action | Path |
|--------|------|
| Create | `src/automana/database/SQL/migrations/migration_63_collection_game_code.sql` |
| Modify | `src/automana/core/repositories/app_integration/shopify/ApiShopify_repository.py` |
| Modify | `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py` |
| Modify | `src/automana/core/services/app_integration/shopify/data_staging_service.py` |
| Modify | `src/automana/core/services/app_integration/shopify/pipeline_service.py` |
| Modify | `src/automana/worker/tasks/pipelines.py` |
| Create | `src/automana/tests/unit/services/shopify/__init__.py` |
| Create | `src/automana/tests/unit/services/shopify/test_shopify_api_repository.py` |
| Create | `src/automana/tests/unit/services/shopify/test_data_staging_service.py` |
| Create | `src/automana/tests/unit/services/shopify/test_pipeline_service.py` |

---

## Task 1: DB Migration — fix URL + add `game_code` column

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_63_collection_game_code.sql`

- [ ] **Step 1: Write the migration**

```sql
-- migration_63_collection_game_code.sql
BEGIN;

-- Fix incorrect store URL set in migration_48
UPDATE markets.market_ref
SET api_url = 'https://tcg.goodgames.com.au'
WHERE name = 'Good Games Brisbane';

-- Add game classification to collection handles
-- NULL = unclassified, 'mtg' = active, 'pokemon'/'lorcana'/etc = stored but ignored
ALTER TABLE markets.collection_handles
    ADD COLUMN IF NOT EXISTS game_code VARCHAR;

COMMIT;
```

- [ ] **Step 2: Apply the migration**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -f /app/src/automana/database/SQL/migrations/migration_63_collection_game_code.sql
```

Expected: `UPDATE 1` then `ALTER TABLE`

- [ ] **Step 3: Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "SELECT name, api_url FROM markets.market_ref WHERE name = 'Good Games Brisbane';"
```

Expected: `api_url = https://tcg.goodgames.com.au`

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "\d markets.collection_handles"
```

Expected: `game_code` column present with type `character varying`.

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_63_collection_game_code.sql
git commit -m "feat(db): add game_code to collection_handles + fix gg-brisbane URL"
```

---

## Task 2: `ShopifyAPIRepository` — sitemap + collection product fetchers

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/ApiShopify_repository.py`
- Create: `src/automana/tests/unit/services/shopify/__init__.py`
- Create: `src/automana/tests/unit/services/shopify/test_shopify_api_repository.py`

- [ ] **Step 1: Write the failing tests**

Create `src/automana/tests/unit/services/shopify/__init__.py` (empty file).

Create `src/automana/tests/unit/services/shopify/test_shopify_api_repository.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from automana.core.repositories.app_integration.shopify.ApiShopify_repository import ShopifyAPIRepository


@pytest.fixture
def repo():
    return ShopifyAPIRepository()


def _mock_response(text="", json_data=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


class TestGetCollectionProductsPage:
    @pytest.mark.asyncio
    async def test_returns_products_list(self, repo):
        products = [{"id": 1, "title": "Ragavan"}, {"id": 2, "title": "Bolt"}]
        mock_resp = _mock_response(json_data={"products": products})

        with patch.object(repo, "send", new=AsyncMock(return_value=mock_resp)):
            result = await repo.get_collection_products_page(
                "https://tcg.goodgames.com.au", "bloomburrow-singles", since_id=0
            )

        assert result == products

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_products(self, repo):
        mock_resp = _mock_response(json_data={"products": []})

        with patch.object(repo, "send", new=AsyncMock(return_value=mock_resp)):
            result = await repo.get_collection_products_page(
                "https://tcg.goodgames.com.au", "bloomburrow-singles", since_id=999
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_passes_since_id_and_limit_as_params(self, repo):
        mock_resp = _mock_response(json_data={"products": []})
        send_mock = AsyncMock(return_value=mock_resp)

        with patch.object(repo, "send", new=send_mock):
            await repo.get_collection_products_page(
                "https://tcg.goodgames.com.au", "magic-the-gathering-singles-in-stock",
                since_id=12345, limit=250
            )

        call_kwargs = send_mock.call_args
        assert call_kwargs.kwargs["params"] == {"limit": 250, "since_id": 12345}


class TestGetSitemapCollectionHandles:
    SITEMAP_XML = """<?xml version="1.0"?>
    <sitemapindex>
      <sitemap><loc>https://tcg.goodgames.com.au/sitemap_collections_1.xml?from=1&amp;to=2</loc></sitemap>
    </sitemapindex>"""

    COLLECTIONS_XML = """<?xml version="1.0"?>
    <urlset>
      <url><loc>https://tcg.goodgames.com.au/collections/bloomburrow-singles</loc></url>
      <url><loc>https://tcg.goodgames.com.au/collections/magic-the-gathering-singles-in-stock</loc></url>
      <url><loc>https://tcg.goodgames.com.au/collections/bloomburrow-singles</loc></url>
    </urlset>"""

    @pytest.mark.asyncio
    async def test_returns_deduplicated_handles(self, repo):
        sitemap_resp = _mock_response(text=self.SITEMAP_XML)
        collections_resp = _mock_response(text=self.COLLECTIONS_XML)
        send_mock = AsyncMock(side_effect=[sitemap_resp, collections_resp])

        with patch.object(repo, "send", new=send_mock):
            async with repo:
                handles = await repo.get_sitemap_collection_handles("https://tcg.goodgames.com.au")

        assert set(handles) == {"bloomburrow-singles", "magic-the-gathering-singles-in-stock"}
        assert len(handles) == 2  # deduped

    @pytest.mark.asyncio
    async def test_handles_multiple_sitemap_pages(self, repo):
        sitemap_two_pages = """<?xml version="1.0"?>
        <sitemapindex>
          <sitemap><loc>https://tcg.goodgames.com.au/sitemap_collections_1.xml</loc></sitemap>
          <sitemap><loc>https://tcg.goodgames.com.au/sitemap_collections_2.xml</loc></sitemap>
        </sitemapindex>"""
        page1 = _mock_response(text='<urlset><url><loc>https://x.com/collections/alpha</loc></url></urlset>')
        page2 = _mock_response(text='<urlset><url><loc>https://x.com/collections/beta</loc></url></urlset>')
        send_mock = AsyncMock(side_effect=[_mock_response(text=sitemap_two_pages), page1, page2])

        with patch.object(repo, "send", new=send_mock):
            async with repo:
                handles = await repo.get_sitemap_collection_handles("https://x.com")

        assert set(handles) == {"alpha", "beta"}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/arthur/projects/AutoMana
python -m pytest src/automana/tests/unit/services/shopify/test_shopify_api_repository.py -v 2>&1 | tail -20
```

Expected: `AttributeError: 'ShopifyAPIRepository' object has no attribute 'get_collection_products_page'`

- [ ] **Step 3: Add the two new methods to `ApiShopify_repository.py`**

Add after the `iter_products_pages` method (line 42):

```python
async def get_collection_products_page(
    self,
    api_url: str,
    handle: str,
    since_id: int = 0,
    limit: int = 250,
) -> list[dict]:
    """Fetch one page of products from a collection via since_id pagination.

    Does NOT manage the HTTP client lifecycle — the caller must hold
    the client open (via ``async with repo:``) across concurrent calls.
    Returns empty list when there are no more products.
    """
    url = f"{api_url.rstrip('/')}/collections/{handle}/products.json"
    response = await self.send("GET", url, params={"limit": limit, "since_id": since_id})
    response.raise_for_status()
    return response.json().get("products", [])

async def get_sitemap_collection_handles(self, api_url: str) -> list[str]:
    """Discover all collection handles from the store's Shopify sitemap.

    Fetches /sitemap.xml, finds sitemap_collections_*.xml links, then
    extracts collection handles from each collections sitemap.
    Returns a deduplicated list of handles.
    """
    import re

    async with self:
        sitemap_resp = await self.send("GET", f"{api_url.rstrip('/')}/sitemap.xml")
        sitemap_resp.raise_for_status()

        collection_sitemap_links = re.findall(
            r"<loc>(https?://[^<]+sitemap_collections_[^<]+)</loc>",
            sitemap_resp.text,
        )

        handles: set[str] = set()
        for link in collection_sitemap_links:
            resp = await self.send("GET", link)
            resp.raise_for_status()
            found = re.findall(r"/collections/([^<\s?#/]+)", resp.text)
            handles.update(found)

    return list(handles)
```

- [ ] **Step 4: Run tests — all pass**

```bash
python -m pytest src/automana/tests/unit/services/shopify/test_shopify_api_repository.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/ApiShopify_repository.py \
        src/automana/tests/unit/services/shopify/__init__.py \
        src/automana/tests/unit/services/shopify/test_shopify_api_repository.py
git commit -m "feat(shopify): add since_id collection fetcher + sitemap handle discovery"
```

---

## Task 3: `ShopifyPipelineRepository` — `get_mtg_collection_handles`

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py`

- [ ] **Step 1: Add the method**

Add after `upsert_product_handles` (after line 65 in pipeline_repository.py):

```python
async def get_mtg_collection_handles(self, market_id: int) -> list[str]:
    """Return collection handles marked game_code='mtg' for the given market."""
    rows = await self.execute_query(
        """
        SELECT name
        FROM markets.collection_handles
        WHERE market_id = $1 AND game_code = 'mtg'
        """,
        (market_id,),
    )
    return [r["name"] for r in rows]
```

- [ ] **Step 2: Verify no import changes needed** — method uses only `self.execute_query` which is inherited from `AbstractRepository`.

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/pipeline_repository.py
git commit -m "feat(shopify): add get_mtg_collection_handles to pipeline repository"
```

---

## Task 4: `data_staging_service.py` — collection tier tagging + priority dedup

**Files:**
- Modify: `src/automana/core/services/app_integration/shopify/data_staging_service.py`
- Create: `src/automana/tests/unit/services/shopify/test_data_staging_service.py`

- [ ] **Step 1: Write the failing tests**

Create `src/automana/tests/unit/services/shopify/test_data_staging_service.py`:

```python
import pandas as pd
import pytest
from automana.core.services.app_integration.shopify.data_staging_service import _dedupe_batch


class TestDedupeWithCollectionTier:
    def test_instock_tier_wins_over_set_tier_when_prices_differ(self):
        df = pd.DataFrame([
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 4.50, "scraped_at": pd.Timestamp("2026-05-01"), "collection_tier": 0},
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 5.00, "scraped_at": pd.Timestamp("2026-05-01"), "collection_tier": 1},
        ])
        result = _dedupe_batch(df)
        assert len(result) == 1
        assert result.iloc[0]["price"] == 5.00

    def test_set_tier_wins_when_only_set_present(self):
        df = pd.DataFrame([
            {"product_id": 2, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 3.00, "scraped_at": pd.Timestamp("2026-05-01"), "collection_tier": 0},
        ])
        result = _dedupe_batch(df)
        assert len(result) == 1
        assert result.iloc[0]["price"] == 3.00

    def test_collection_tier_column_is_dropped_from_result(self):
        df = pd.DataFrame([
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 5.00, "scraped_at": pd.Timestamp("2026-05-01"), "collection_tier": 1},
        ])
        result = _dedupe_batch(df)
        assert "collection_tier" not in result.columns

    def test_no_collection_tier_column_still_dedupes(self):
        """Backwards compatibility: existing parquet files without collection_tier still work."""
        df = pd.DataFrame([
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 4.00, "scraped_at": pd.Timestamp("2026-05-01 10:00")},
            {"product_id": 1, "date": pd.Timestamp("2026-05-01"), "variation": "Near Mint",
             "price": 4.50, "scraped_at": pd.Timestamp("2026-05-01 11:00")},
        ])
        result = _dedupe_batch(df)
        assert len(result) == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest src/automana/tests/unit/services/shopify/test_data_staging_service.py -v 2>&1 | tail -15
```

Expected: `test_instock_tier_wins_over_set_tier_when_prices_differ` FAILED — `collection_tier` not in sort columns.

- [ ] **Step 3: Update `_dedupe_batch` in `data_staging_service.py`**

Replace lines 80–86:

```python
def _dedupe_batch(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    sort_cols = ["product_id", "date", "variation"]
    if "collection_tier" in df.columns:
        sort_cols.append("collection_tier")
    else:
        sort_cols.append("scraped_at")
    result = (
        df.sort_values(sort_cols)
        .drop_duplicates(["product_id", "date", "variation"], keep="last")
    )
    if "collection_tier" in result.columns:
        result = result.drop(columns=["collection_tier"])
    return result
```

- [ ] **Step 4: Run tests — all pass**

```bash
python -m pytest src/automana/tests/unit/services/shopify/test_data_staging_service.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Add `collection_tier` tagging in `process_json_dir_to_parquet`**

In `data_staging_service.py`, inside the `for file_index, json_file in enumerate(json_files, 1):` loop, add the collection handle read and tier derivation **before** the `with open(json_file, "rb") as f:` block:

```python
# Read collection handle embedded in JSON metadata to derive dedup priority.
# _collection_handle is written first in the payload by fetch_all_markets so
# ijson finds it before scanning the (large) items array.
_collection_handle = ""
with open(json_file, "rb") as _fh:
    _collection_handle = next(ijson.items(_fh, "_collection_handle"), "")
_collection_tier = 1 if "in-stock" in _collection_handle or "instock" in _collection_handle else 0
```

Then inside the item processing loop, after `df_item = _df_from_item(item)` and the empty check, add:

```python
df_item["collection_tier"] = _collection_tier
```

The full changed block (lines 229–244) becomes:

```python
        # Read collection handle for dedup priority
        _collection_handle = ""
        with open(json_file, "rb") as _fh:
            _collection_handle = next(ijson.items(_fh, "_collection_handle"), "")
        _collection_tier = 1 if "in-stock" in _collection_handle or "instock" in _collection_handle else 0

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

                    df_item["collection_tier"] = _collection_tier
                    meta_data = await extract_all_metadata_from_html(item.get("body_html", ""))
                    df_item["card_id"] = meta_data.get("card_id")
                    df_item["tcg_id"] = meta_data.get("tcg_id")
                    buffers[pid].append(df_item)
```

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/app_integration/shopify/data_staging_service.py \
        src/automana/tests/unit/services/shopify/test_data_staging_service.py
git commit -m "feat(shopify): collection_tier priority dedup — instock price wins over per-set"
```

---

## Task 5: `pipeline_service.py` — add `fetch_collections` service

**Files:**
- Modify: `src/automana/core/services/app_integration/shopify/pipeline_service.py`
- Create: `src/automana/tests/unit/services/shopify/test_pipeline_service.py`

- [ ] **Step 1: Write the failing tests**

Create `src/automana/tests/unit/services/shopify/test_pipeline_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestFetchCollections:
    @pytest.mark.asyncio
    async def test_fetches_sitemap_and_upserts_handles(self):
        from automana.core.services.app_integration.shopify.pipeline_service import fetch_collections

        pipeline_repo = AsyncMock()
        pipeline_repo.get_active_pipeline_markets = AsyncMock(return_value=[
            {"market_id": 1, "name": "GG Brisbane", "api_url": "https://tcg.goodgames.com.au",
             "source_id": 1727, "source_code": "gg_brisbane"},
        ])
        collection_repo = AsyncMock()
        ops_repo = AsyncMock()
        ops_repo.__aenter__ = AsyncMock(return_value=ops_repo)
        ops_repo.__aexit__ = AsyncMock(return_value=False)
        api_repo = AsyncMock()
        api_repo.get_sitemap_collection_handles = AsyncMock(
            return_value=["magic-the-gathering-singles-in-stock", "bloomburrow-singles"]
        )

        with patch(
            "automana.core.services.app_integration.shopify.pipeline_service.track_step",
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)),
        ):
            result = await fetch_collections(
                shopify_pipeline_repository=pipeline_repo,
                collection_repository=collection_repo,
                ops_repository=ops_repo,
                shopify_api_repository=api_repo,
                ingestion_run_id=42,
            )

        api_repo.get_sitemap_collection_handles.assert_awaited_once_with("https://tcg.goodgames.com.au")
        collection_repo.add_many.assert_awaited_once()
        rows_passed = collection_repo.add_many.call_args[0][0]
        assert len(rows_passed) == 2
        assert any(r["name"] == "magic-the-gathering-singles-in-stock" for r in rows_passed)
        assert result["collections_synced"] == 2

    @pytest.mark.asyncio
    async def test_no_active_markets_returns_zero(self):
        from automana.core.services.app_integration.shopify.pipeline_service import fetch_collections

        pipeline_repo = AsyncMock()
        pipeline_repo.get_active_pipeline_markets = AsyncMock(return_value=[])
        collection_repo = AsyncMock()

        result = await fetch_collections(
            shopify_pipeline_repository=pipeline_repo,
            collection_repository=collection_repo,
            ops_repository=AsyncMock(),
            shopify_api_repository=AsyncMock(),
            ingestion_run_id=None,
        )

        collection_repo.add_many.assert_not_awaited()
        assert result["collections_synced"] == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest src/automana/tests/unit/services/shopify/test_pipeline_service.py::TestFetchCollections -v 2>&1 | tail -10
```

Expected: `ImportError` or `AttributeError` — `fetch_collections` doesn't exist yet.

- [ ] **Step 3: Add `fetch_collections` to `pipeline_service.py`**

Add these two imports at the top of `pipeline_service.py` (after the existing imports):

```python
from automana.core.repositories.app_integration.shopify.collection_repository import ShopifyCollectionRepository
from automana.core.models.shopify.shopify_theme import InsertCollection
```

Add the new service function after the existing imports and before `fetch_all_markets`:

```python
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

    After the first run, the operator classifies MTG collections:
        UPDATE markets.collection_handles SET game_code = 'mtg'
        WHERE market_id = X AND name IN ('magic-the-gathering-singles-in-stock', ...);
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
```

- [ ] **Step 4: Run tests — all pass**

```bash
python -m pytest src/automana/tests/unit/services/shopify/test_pipeline_service.py::TestFetchCollections -v
```

Expected: 2 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/shopify/pipeline_service.py \
        src/automana/tests/unit/services/shopify/test_pipeline_service.py
git commit -m "feat(shopify): add fetch_collections pipeline service via sitemap discovery"
```

---

## Task 6: `pipeline_service.py` — replace `fetch_all_markets` with collection-based + `since_id`

**Files:**
- Modify: `src/automana/core/services/app_integration/shopify/pipeline_service.py`

- [ ] **Step 1: Write the failing tests** (add to existing `test_pipeline_service.py`)

```python
class TestFetchAllMarkets:
    @pytest.mark.asyncio
    async def test_skips_market_with_no_mtg_collections(self):
        from automana.core.services.app_integration.shopify.pipeline_service import fetch_all_markets

        pipeline_repo = AsyncMock()
        pipeline_repo.get_active_pipeline_markets = AsyncMock(return_value=[
            {"market_id": 1, "api_url": "https://tcg.goodgames.com.au",
             "source_id": 1727, "source_code": "gg_brisbane"},
        ])
        pipeline_repo.get_mtg_collection_handles = AsyncMock(return_value=[])
        api_repo = AsyncMock()
        storage = AsyncMock()

        result = await fetch_all_markets(
            shopify_pipeline_repository=pipeline_repo,
            ops_repository=AsyncMock(),
            shopify_api_repository=api_repo,
            storage_service=storage,
            ingestion_run_id=None,
        )

        api_repo.get_collection_products_page.assert_not_awaited()
        assert result["market_dirs"] == {}

    @pytest.mark.asyncio
    async def test_fetches_products_per_collection_via_since_id(self):
        from automana.core.services.app_integration.shopify.pipeline_service import fetch_all_markets

        page1 = [{"id": 100, "title": "Ragavan"}, {"id": 200, "title": "Bolt"}]
        pipeline_repo = AsyncMock()
        pipeline_repo.get_active_pipeline_markets = AsyncMock(return_value=[
            {"market_id": 1, "api_url": "https://tcg.goodgames.com.au",
             "source_id": 1727, "source_code": "gg_brisbane"},
        ])
        pipeline_repo.get_mtg_collection_handles = AsyncMock(return_value=["bloomburrow-singles"])
        # First call returns page1, second call (since_id=200) returns empty → stops
        api_repo = AsyncMock()
        api_repo.__aenter__ = AsyncMock(return_value=api_repo)
        api_repo.__aexit__ = AsyncMock(return_value=False)
        api_repo.get_collection_products_page = AsyncMock(side_effect=[page1, []])
        storage = AsyncMock()
        storage.backend = MagicMock()
        storage.backend.resolve_path = MagicMock(return_value=MagicMock(__str__=lambda s: "/tmp/shopify/1727_fetch"))

        with patch(
            "automana.core.services.app_integration.shopify.pipeline_service.track_step",
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)),
        ):
            result = await fetch_all_markets(
                shopify_pipeline_repository=pipeline_repo,
                ops_repository=AsyncMock(),
                shopify_api_repository=api_repo,
                storage_service=storage,
                ingestion_run_id=42,
            )

        # since_id=0 first call, then since_id=200 (last product id)
        calls = api_repo.get_collection_products_page.call_args_list
        assert calls[0].args == ("https://tcg.goodgames.com.au", "bloomburrow-singles")
        assert calls[0].kwargs["since_id"] == 0
        assert calls[1].kwargs["since_id"] == 200
        # JSON saved once (one page of products)
        storage.save_json.assert_awaited_once()
        saved_path = storage.save_json.call_args[0][0]
        assert "bloomburrow-singles_page_0_products.json" in saved_path
        assert 1 in result["market_dirs"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest src/automana/tests/unit/services/shopify/test_pipeline_service.py::TestFetchAllMarkets -v 2>&1 | tail -15
```

Expected: FAILED — `fetch_all_markets` still uses old `iter_products_pages` logic.

- [ ] **Step 3: Replace `fetch_all_markets` in `pipeline_service.py`**

Replace the entire `fetch_all_markets` function (lines 78–113) with:

```python
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
    import asyncio

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
```

- [ ] **Step 4: Run all pipeline service tests**

```bash
python -m pytest src/automana/tests/unit/services/shopify/test_pipeline_service.py -v
```

Expected: all 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/shopify/pipeline_service.py \
        src/automana/tests/unit/services/shopify/test_pipeline_service.py
git commit -m "feat(shopify): replace /products.json with collection-based since_id fetch"
```

---

## Task 7: `pipelines.py` — wire `fetch_collections` into the Celery chain

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py`

- [ ] **Step 1: Update `shopify_weekly_pipeline` in `pipelines.py`**

Replace lines 288–301:

```python
    wf = chain(
        run_service.s(
            "ops.pipeline_services.start_run",
            pipeline_name="shopify_weekly",
            source_name="shopify",
            run_key=run_key,
            celery_task_id=self.request.id,
        ),
        run_service.s("shopify.pipeline.fetch_collections"),
        run_service.s("shopify.pipeline.fetch_all_markets"),
        run_service.s("shopify.pipeline.process_to_parquet"),
        run_service.s("shopify.pipeline.stage_raw"),
        run_service.s("shopify.pipeline.promote_observations"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
```

Also update the docstring (lines 274–279) to reflect the new step:

```python
    """Weekly Celery Beat job: discover collections via sitemap, fetch
    /collections/{handle}/products.json for MTG-classified collections,
    process to parquet, stage into pricing.shopify_staging_raw, and
    promote into pricing.price_observation.

    Per project rules this task does NOT use ``autoretry_for``; retry policy
    lives at the run_service layer.

    First run: fetch_collections populates markets.collection_handles.
    Operator must then classify MTG collections before products are fetched.
    """
```

- [ ] **Step 2: Run the full test suite for pipelines**

```bash
python -m pytest src/automana/tests/unit/tasks/ -v 2>&1 | tail -20
```

Expected: all existing pipeline tests still PASS.

- [ ] **Step 3: Commit**

```bash
git add src/automana/worker/tasks/pipelines.py
git commit -m "feat(shopify): wire fetch_collections into weekly pipeline chain"
```

---

## Task 8: Run all tests + smoke verify

- [ ] **Step 1: Full test suite**

```bash
python -m pytest src/automana/tests/ -v 2>&1 | tail -30
```

Expected: all tests PASS, no regressions.

- [ ] **Step 2: Manual first-run smoke test** (requires running stack)

```bash
# Trigger the pipeline manually via Celery
docker exec automana-celery-worker-dev python -c "
from automana.worker.tasks.pipelines import shopify_weekly_pipeline
result = shopify_weekly_pipeline.apply()
print('task id:', result.id if hasattr(result, 'id') else result)
"
```

- [ ] **Step 3: Check collections were discovered**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT COUNT(*), game_code
FROM markets.collection_handles ch
JOIN markets.market_ref mr ON mr.market_id = ch.market_id
WHERE mr.name = 'Good Games Brisbane'
GROUP BY game_code;"
```

Expected: ~447 rows with `game_code = NULL`.

- [ ] **Step 4: Classify MTG collections**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
UPDATE markets.collection_handles
SET game_code = 'mtg'
WHERE market_id = (SELECT market_id FROM markets.market_ref WHERE name = 'Good Games Brisbane')
  AND name = 'magic-the-gathering-singles-in-stock';

UPDATE markets.collection_handles
SET game_code = 'mtg'
WHERE market_id = (SELECT market_id FROM markets.market_ref WHERE name = 'Good Games Brisbane')
  AND name ILIKE ANY(ARRAY['%-singles', '%-mtg-singles', 'mtg-singles-%', 'commander-staples'])
  AND name NOT ILIKE ANY(ARRAY['%-sealed%', '%-booster%', '%-pack%', 'pokemon%', 'lorcana%',
                                'flesh-and-blood%', 'one-piece%', 'digimon%']);"
```

- [ ] **Step 5: Trigger second run and verify price observations**

```bash
# Manually re-trigger (or wait for Sunday beat schedule)
# Then check promote worked:
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT COUNT(DISTINCT sp.source_product_id)
FROM pricing.price_observation po
JOIN pricing.source_product sp ON sp.source_product_id = po.source_product_id
JOIN pricing.price_source ps ON ps.source_id = sp.source_id
WHERE ps.code = 'gg_brisbane';"
```

Expected: count > 0. A count > 1000 indicates healthy pipeline coverage.

- [ ] **Step 6: Final commit if any fixes were made**

```bash
git add -p  # stage only intentional fixes
git commit -m "fix(shopify): post-smoke-test corrections"
```
