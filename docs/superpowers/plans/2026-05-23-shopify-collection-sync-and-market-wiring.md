# Shopify Collection Sync + Market Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire GG Sydney and GG Brisbane into the Shopify pipeline, add an efficient collection-sync step (2 REST calls per market), and fix three bugs that would silently break the pipeline on first run.

**Architecture:** A new `fetch_collections` Celery step runs before `fetch_all_markets`, paginating Shopify's `/custom_collections.json` and `/smart_collections.json` endpoints and batch-upserting handles into `markets.collection_handles`. Three schema-prefix and COMMIT bugs in existing repos are patched in the same pass.

**Tech Stack:** asyncpg, httpx, Celery chain, pytest (asyncio_mode=auto), FastParquet, pandas

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `src/automana/database/SQL/migrations/migration_48_wire_gg_markets.sql` | Wire source_id on GG Sydney, insert GG Brisbane market row |
| Modify | `src/automana/core/repositories/app_integration/shopify/market_repository.py` | Fix missing `pricing.` schema prefix in `get_market_code` |
| Modify | `src/automana/core/repositories/app_integration/shopify/product_repository.py` | Fix table schema prefix + remove manual COMMIT |
| Modify | `src/automana/core/repositories/app_integration/shopify/ApiShopify_repository.py` | Add `iter_collection_pages` async generator |
| Modify | `src/automana/core/repositories/app_integration/shopify/collection_repository.py` | Add `upsert_many` method |
| Modify | `src/automana/core/services/app_integration/shopify/pipeline_service.py` | Add `fetch_collections` service function |
| Modify | `src/automana/worker/tasks/pipelines.py` | Prepend `fetch_collections` step to Celery chain |
| Create | `tests/unit/core/test_shopify_collection_fetch.py` | Unit tests for new and fixed code |

---

## Task 1: DB Migration — Wire Markets

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_48_wire_gg_markets.sql`

Background: `migration_46_shopify_market_pipeline.sql` already added the `source_id` column and inserted both price source rows (`gg_sydney` source_id=1728, `gg_brisbane` source_id=1727). The UPDATEs in that migration silently no-oped because the market rows were inserted later. This migration completes the wiring.

- [ ] **Step 1: Create the migration file**

```sql
-- src/automana/database/SQL/migrations/migration_48_wire_gg_markets.sql
BEGIN;

-- Wire GG Sydney (market row exists, source row exists, source_id is NULL)
UPDATE markets.market_ref
SET source_id = (
    SELECT source_id FROM pricing.price_source WHERE code = 'gg_sydney'
)
WHERE name = 'Good Games Sydney'
  AND source_id IS NULL;

-- Add GG Brisbane (source row already exists from migration_46)
INSERT INTO markets.market_ref (name, city, country_code, api_url, source_id)
SELECT
    'Good Games Brisbane',
    'Brisbane',
    'AUD',
    'https://gg-brisbane.myshopify.com',
    source_id
FROM pricing.price_source
WHERE code = 'gg_brisbane'
ON CONFLICT (name) DO NOTHING;

COMMIT;
```

- [ ] **Step 2: Apply the migration**

```bash
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --preserve-data
```

This applies all pending migrations incrementally without dropping data. The script picks up `migration_48_wire_gg_markets.sql` automatically.

- [ ] **Step 3: Verify wiring**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "SELECT market_id, name, api_url, source_id FROM markets.market_ref ORDER BY market_id;"
```

Expected:
```
 market_id |        name         |              api_url               | source_id
-----------+---------------------+------------------------------------+-----------
         1 | TestMarket          | https://test.myshopify.com         |
         2 | Good Games Sydney   | https://gg-sydney.myshopify.com    |      1728
         3 | Good Games Brisbane | https://gg-brisbane.myshopify.com  |      1727
```
(market_id for Brisbane may differ)

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_48_wire_gg_markets.sql
git commit -m "feat(shopify): migration_48 — wire GG Sydney source_id + add GG Brisbane market"
```

---

## Task 2: Fix Three Repository Bugs

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/market_repository.py:22`
- Modify: `src/automana/core/repositories/app_integration/shopify/product_repository.py:26-27`
- Create: `tests/unit/core/test_shopify_collection_fetch.py`

These bugs cause silent failures: wrong schema names make queries fail at runtime; the spurious COMMIT on an asyncpg connection is a no-op at best and can corrupt transaction state at worst.

- [ ] **Step 1: Write the failing tests first**

Create `tests/unit/core/test_shopify_collection_fetch.py`:

```python
"""Unit tests for Shopify collection sync and repository bug fixes."""
import io
import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from automana.core.repositories.app_integration.shopify.market_repository import MarketRepository
from automana.core.repositories.app_integration.shopify.product_repository import ProductRepository


# ── Bug fix tests ─────────────────────────────────────────────────────────────

async def test_get_market_code_uses_pricing_schema():
    """get_market_code must query pricing.price_source, not bare price_source."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[{"source_id": 1728}])
    repo = MarketRepository(connection=mock_conn, executor=None)

    result = await repo.get_market_code("gg_sydney")

    assert result == 1728
    sql_used = mock_conn.fetch.call_args[0][0]
    assert "pricing.price_source" in sql_used, (
        f"Expected 'pricing.price_source' in query, got: {sql_used!r}"
    )


async def test_bulk_copy_prices_uses_pricing_schema():
    """bulk_copy_prices must copy into pricing.shopify_staging_raw, not bare name."""
    mock_conn = AsyncMock()
    mock_conn.copy_to_table = AsyncMock()
    mock_conn.execute = AsyncMock()
    repo = ProductRepository(connection=mock_conn, executor=None)
    df = pd.DataFrame({
        "product_id": [1], "date": ["2026-05-23"], "variation": ["Near Mint"],
        "price": [4.99], "scraped_at": ["2026-05-23"],
    })

    await repo.bulk_copy_prices(df)

    table_arg = mock_conn.copy_to_table.call_args[0][0]
    assert table_arg == "pricing.shopify_staging_raw", (
        f"Expected 'pricing.shopify_staging_raw', got: {table_arg!r}"
    )


async def test_bulk_copy_prices_does_not_commit():
    """bulk_copy_prices must not issue a manual COMMIT on the asyncpg connection."""
    mock_conn = AsyncMock()
    mock_conn.copy_to_table = AsyncMock()
    mock_conn.execute = AsyncMock()
    repo = ProductRepository(connection=mock_conn, executor=None)
    df = pd.DataFrame({
        "product_id": [1], "date": ["2026-05-23"], "variation": ["Near Mint"],
        "price": [4.99], "scraped_at": ["2026-05-23"],
    })

    await repo.bulk_copy_prices(df)

    for c in mock_conn.execute.call_args_list:
        sql = c[0][0] if c[0] else ""
        assert "COMMIT" not in sql.upper(), "bulk_copy_prices must not issue COMMIT"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/unit/core/test_shopify_collection_fetch.py::test_get_market_code_uses_pricing_schema \
       tests/unit/core/test_shopify_collection_fetch.py::test_bulk_copy_prices_uses_pricing_schema \
       tests/unit/core/test_shopify_collection_fetch.py::test_bulk_copy_prices_does_not_commit \
       -v
```

Expected: all three FAIL — the current code uses wrong schema names and issues COMMIT.

- [ ] **Step 3: Fix `market_repository.py` — schema prefix**

In `src/automana/core/repositories/app_integration/shopify/market_repository.py`, change line ~23:

```python
# Before:
async def get_market_code(self, name: str) -> Optional[str]:
    query = "SELECT source_id FROM price_source WHERE code = $1;"
    result = await self.execute_query(query, (name,))
    return result[0].get('source_id') if result else None

# After:
async def get_market_code(self, name: str) -> Optional[str]:
    query = "SELECT source_id FROM pricing.price_source WHERE code = $1;"
    result = await self.execute_query(query, (name,))
    return result[0].get('source_id') if result else None
```

- [ ] **Step 4: Fix `product_repository.py` — schema prefix and remove COMMIT**

In `src/automana/core/repositories/app_integration/shopify/product_repository.py`, replace `bulk_copy_prices`:

```python
async def bulk_copy_prices(self, df):
    await self._copy_to_table(df, "pricing.shopify_staging_raw")
```

(Remove the `await self.connection.execute('COMMIT;')` line entirely.)

- [ ] **Step 5: Run tests — expect all three pass**

```bash
pytest tests/unit/core/test_shopify_collection_fetch.py::test_get_market_code_uses_pricing_schema \
       tests/unit/core/test_shopify_collection_fetch.py::test_bulk_copy_prices_uses_pricing_schema \
       tests/unit/core/test_shopify_collection_fetch.py::test_bulk_copy_prices_does_not_commit \
       -v
```

Expected: all three PASS.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/market_repository.py \
        src/automana/core/repositories/app_integration/shopify/product_repository.py \
        tests/unit/core/test_shopify_collection_fetch.py
git commit -m "fix(shopify): schema prefix in get_market_code + bulk_copy_prices, remove spurious COMMIT"
```

---

## Task 3: Add `iter_collection_pages` to `ShopifyAPIRepository`

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/ApiShopify_repository.py`
- Modify: `tests/unit/core/test_shopify_collection_fetch.py`

This method follows the exact same Link-header pagination pattern as `iter_products_pages`. It yields one page (a list of collection dicts) per Shopify API response.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/core/test_shopify_collection_fetch.py`:

```python
import httpx
from automana.core.repositories.app_integration.shopify.ApiShopify_repository import ShopifyAPIRepository


def _mock_response(data: dict, link: str = "") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.headers = {"link": link}
    resp.raise_for_status = MagicMock()
    return resp


async def test_iter_collection_pages_single_page():
    """Yields one page and stops when no Link header is present."""
    repo = ShopifyAPIRepository()
    page_data = [{"id": 1, "handle": "commander", "title": "Commander"}]
    repo.send = AsyncMock(return_value=_mock_response({"custom_collections": page_data}))
    repo.__aenter__ = AsyncMock(return_value=repo)
    repo.__aexit__ = AsyncMock(return_value=False)

    pages = []
    async for page in repo.iter_collection_pages("https://gg-sydney.myshopify.com", "custom_collections"):
        pages.append(page)

    assert len(pages) == 1
    assert pages[0] == page_data
    assert repo.send.call_count == 1
    called_url = repo.send.call_args[0][1]
    assert "custom_collections.json" in called_url
    assert "limit=250" in called_url


async def test_iter_collection_pages_follows_link_header():
    """Follows the rel='next' Link header to fetch a second page."""
    repo = ShopifyAPIRepository()
    page1 = [{"id": 1, "handle": "modern", "title": "Modern"}]
    page2 = [{"id": 2, "handle": "legacy", "title": "Legacy"}]
    next_url = "https://gg-sydney.myshopify.com/custom_collections.json?page_info=abc&limit=250"
    repo.send = AsyncMock(side_effect=[
        _mock_response({"custom_collections": page1}, link=f'<{next_url}>; rel="next"'),
        _mock_response({"custom_collections": page2}),
    ])
    repo.__aenter__ = AsyncMock(return_value=repo)
    repo.__aexit__ = AsyncMock(return_value=False)

    pages = []
    async for page in repo.iter_collection_pages("https://gg-sydney.myshopify.com", "custom_collections"):
        pages.append(page)

    assert len(pages) == 2
    assert pages[0] == page1
    assert pages[1] == page2
    assert repo.send.call_count == 2
    second_call_url = repo.send.call_args_list[1][0][1]
    assert second_call_url == next_url


async def test_iter_collection_pages_stops_on_empty_response():
    """Stops immediately when Shopify returns an empty collection list."""
    repo = ShopifyAPIRepository()
    repo.send = AsyncMock(return_value=_mock_response({"custom_collections": []}))
    repo.__aenter__ = AsyncMock(return_value=repo)
    repo.__aexit__ = AsyncMock(return_value=False)

    pages = []
    async for page in repo.iter_collection_pages("https://gg-sydney.myshopify.com", "custom_collections"):
        pages.append(page)

    assert pages == []
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/unit/core/test_shopify_collection_fetch.py::test_iter_collection_pages_single_page \
       tests/unit/core/test_shopify_collection_fetch.py::test_iter_collection_pages_follows_link_header \
       tests/unit/core/test_shopify_collection_fetch.py::test_iter_collection_pages_stops_on_empty_response \
       -v
```

Expected: FAIL with `AttributeError: iter_collection_pages`.

- [ ] **Step 3: Implement `iter_collection_pages`**

In `src/automana/core/repositories/app_integration/shopify/ApiShopify_repository.py`, add after `iter_products_pages`:

```python
async def iter_collection_pages(
    self, api_url: str, endpoint: str
):
    """Paginate a Shopify collection endpoint, yielding one page per response.

    Args:
        api_url: Store base URL, e.g. "https://gg-sydney.myshopify.com"
        endpoint: "custom_collections" or "smart_collections"

    Yields:
        list[dict] — one page of collection records
    """
    next_url = f"{api_url.rstrip('/')}/{endpoint}.json?limit=250"
    async with self:
        while next_url:
            response = await self.send("GET", next_url)
            response.raise_for_status()
            data = response.json()
            collections = data.get(endpoint) or []
            if not collections:
                break
            yield collections
            link_header = response.headers.get("link", "")
            next_url = None
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    break
```

- [ ] **Step 4: Run tests — expect all three pass**

```bash
pytest tests/unit/core/test_shopify_collection_fetch.py::test_iter_collection_pages_single_page \
       tests/unit/core/test_shopify_collection_fetch.py::test_iter_collection_pages_follows_link_header \
       tests/unit/core/test_shopify_collection_fetch.py::test_iter_collection_pages_stops_on_empty_response \
       -v
```

Expected: all three PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/ApiShopify_repository.py \
        tests/unit/core/test_shopify_collection_fetch.py
git commit -m "feat(shopify): add iter_collection_pages to ShopifyAPIRepository"
```

---

## Task 4: Add `upsert_many` to `ShopifyCollectionRepository`

**Files:**
- Modify: `src/automana/core/repositories/app_integration/shopify/collection_repository.py`
- Modify: `tests/unit/core/test_shopify_collection_fetch.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/core/test_shopify_collection_fetch.py`:

```python
from automana.core.repositories.app_integration.shopify.collection_repository import ShopifyCollectionRepository


async def test_upsert_many_skips_empty_list():
    """upsert_many does nothing when passed an empty list."""
    mock_conn = AsyncMock()
    repo = ShopifyCollectionRepository(connection=mock_conn, executor=None)

    await repo.upsert_many([])

    mock_conn.executemany.assert_not_called()


async def test_upsert_many_calls_execute_many_with_correct_args():
    """upsert_many passes (market_id, name) tuples to executemany with upsert SQL."""
    mock_conn = AsyncMock()
    mock_conn.executemany = AsyncMock()
    repo = ShopifyCollectionRepository(connection=mock_conn, executor=None)
    rows = [
        {"market_id": 2, "name": "commander"},
        {"market_id": 2, "name": "modern"},
    ]

    await repo.upsert_many(rows)

    mock_conn.executemany.assert_called_once()
    sql, params = mock_conn.executemany.call_args[0]
    assert "markets.collection_handles" in sql
    assert "ON CONFLICT" in sql
    assert "updated_at" in sql
    assert params == [(2, "commander"), (2, "modern")]
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/unit/core/test_shopify_collection_fetch.py::test_upsert_many_skips_empty_list \
       tests/unit/core/test_shopify_collection_fetch.py::test_upsert_many_calls_execute_many_with_correct_args \
       -v
```

Expected: FAIL with `AttributeError: upsert_many`.

- [ ] **Step 3: Implement `upsert_many`**

In `src/automana/core/repositories/app_integration/shopify/collection_repository.py`, add after the `list` method:

```python
async def upsert_many(self, rows: list[dict]) -> None:
    """Upsert collection handles for a market in one round-trip.

    Args:
        rows: [{"market_id": int, "name": str}, ...]
    """
    if not rows:
        return
    await self.connection.executemany(
        """
        INSERT INTO markets.collection_handles (market_id, name)
        VALUES ($1, $2)
        ON CONFLICT (market_id, name) DO UPDATE SET updated_at = NOW()
        """,
        [(r["market_id"], r["name"]) for r in rows],
    )
```

- [ ] **Step 4: Run tests — expect both pass**

```bash
pytest tests/unit/core/test_shopify_collection_fetch.py::test_upsert_many_skips_empty_list \
       tests/unit/core/test_shopify_collection_fetch.py::test_upsert_many_calls_execute_many_with_correct_args \
       -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/shopify/collection_repository.py \
        tests/unit/core/test_shopify_collection_fetch.py
git commit -m "feat(shopify): add upsert_many to ShopifyCollectionRepository"
```

---

## Task 5: Add `fetch_collections` Pipeline Service

**Files:**
- Modify: `src/automana/core/services/app_integration/shopify/pipeline_service.py`
- Modify: `tests/unit/core/test_shopify_collection_fetch.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/core/test_shopify_collection_fetch.py`:

```python
from automana.core.services.app_integration.shopify.pipeline_service import fetch_collections


async def _run_fetch_collections(
    markets, api_pages_by_endpoint, expect_upsert_rows=None
):
    """Helper: run fetch_collections with full mocks, return result."""
    mock_pipeline_repo = AsyncMock()
    mock_pipeline_repo.get_active_pipeline_markets = AsyncMock(return_value=markets)

    mock_collection_repo = AsyncMock()
    mock_collection_repo.upsert_many = AsyncMock()

    mock_ops_repo = AsyncMock()

    async def _iter_pages(api_url, endpoint):
        for page in api_pages_by_endpoint.get(endpoint, []):
            yield page

    mock_api_repo = MagicMock()
    mock_api_repo.iter_collection_pages = _iter_pages

    result = await fetch_collections(
        shopify_pipeline_repository=mock_pipeline_repo,
        collection_repository=mock_collection_repo,
        ops_repository=mock_ops_repo,
        shopify_api_repository=mock_api_repo,
        ingestion_run_id=42,
    )
    return result, mock_collection_repo


async def test_fetch_collections_syncs_one_market():
    """fetch_collections upserts handles from both collection types for a market."""
    markets = [{"market_id": 2, "api_url": "https://gg-sydney.myshopify.com"}]
    pages = {
        "custom_collections": [[
            {"handle": "commander", "title": "Commander"},
            {"handle": "modern",    "title": "Modern"},
        ]],
        "smart_collections": [[
            {"handle": "legacy",    "title": "Legacy"},
        ]],
    }

    result, mock_collection_repo = await _run_fetch_collections(markets, pages)

    assert result["collections_synced"] == 3
    upserted = mock_collection_repo.upsert_many.call_args[0][0]
    handles = {r["name"] for r in upserted}
    assert handles == {"commander", "modern", "legacy"}
    assert all(r["market_id"] == 2 for r in upserted)


async def test_fetch_collections_deduplicates_handles():
    """A handle that appears in both custom and smart collections is stored once."""
    markets = [{"market_id": 2, "api_url": "https://gg-sydney.myshopify.com"}]
    pages = {
        "custom_collections": [[{"handle": "featured", "title": "Featured"}]],
        "smart_collections": [[{"handle": "featured", "title": "Featured Smart"}]],
    }

    result, mock_collection_repo = await _run_fetch_collections(markets, pages)

    assert result["collections_synced"] == 1
    upserted = mock_collection_repo.upsert_many.call_args[0][0]
    assert len(upserted) == 1
    assert upserted[0]["name"] == "featured"


async def test_fetch_collections_continues_after_http_error():
    """An HTTP error on one endpoint logs a warning and continues to the next."""
    markets = [{"market_id": 2, "api_url": "https://gg-sydney.myshopify.com"}]

    async def _iter_pages_with_error(api_url, endpoint):
        if endpoint == "custom_collections":
            raise httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock(status_code=403)
            )
        yield [{"handle": "modern", "title": "Modern"}]

    mock_pipeline_repo = AsyncMock()
    mock_pipeline_repo.get_active_pipeline_markets = AsyncMock(return_value=markets)
    mock_collection_repo = AsyncMock()
    mock_collection_repo.upsert_many = AsyncMock()
    mock_api_repo = MagicMock()
    mock_api_repo.iter_collection_pages = _iter_pages_with_error

    result = await fetch_collections(
        shopify_pipeline_repository=mock_pipeline_repo,
        collection_repository=mock_collection_repo,
        ops_repository=AsyncMock(),
        shopify_api_repository=mock_api_repo,
        ingestion_run_id=42,
    )

    assert result["collections_synced"] == 1
    upserted = mock_collection_repo.upsert_many.call_args[0][0]
    assert upserted[0]["name"] == "modern"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/unit/core/test_shopify_collection_fetch.py::test_fetch_collections_syncs_one_market \
       tests/unit/core/test_shopify_collection_fetch.py::test_fetch_collections_deduplicates_handles \
       tests/unit/core/test_shopify_collection_fetch.py::test_fetch_collections_continues_after_http_error \
       -v
```

Expected: FAIL with `ImportError` (function doesn't exist yet).

- [ ] **Step 3: Implement `fetch_collections`**

In `src/automana/core/services/app_integration/shopify/pipeline_service.py`, add these imports at the top alongside the existing ones:

```python
from automana.core.repositories.app_integration.shopify.collection_repository import ShopifyCollectionRepository
```

Then add the following function **before** `fetch_all_markets`:

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
    markets = await shopify_pipeline_repository.get_active_pipeline_markets()
    total_synced = 0

    for market in markets:
        market_id = market["market_id"]
        api_url = market["api_url"]

        async with track_step(ops_repository, ingestion_run_id, f"fetch_collections_{market_id}"):
            seen: set[str] = set()
            rows: list[dict] = []

            for endpoint in ("custom_collections", "smart_collections"):
                try:
                    async for page in shopify_api_repository.iter_collection_pages(api_url, endpoint):
                        for col in page:
                            handle = col.get("handle")
                            if handle and handle not in seen:
                                seen.add(handle)
                                rows.append({"market_id": market_id, "name": handle})
                except Exception as e:
                    logger.warning(
                        "shopify_collections_fetch_error",
                        extra={"market_id": market_id, "endpoint": endpoint, "error": str(e)},
                    )

            await collection_repository.upsert_many(rows)
            total_synced += len(rows)
            logger.info(
                "shopify_collections_synced",
                extra={"market_id": market_id, "count": len(rows)},
            )

    return {"collections_synced": total_synced}
```

- [ ] **Step 4: Run tests — expect all three pass**

```bash
pytest tests/unit/core/test_shopify_collection_fetch.py::test_fetch_collections_syncs_one_market \
       tests/unit/core/test_shopify_collection_fetch.py::test_fetch_collections_deduplicates_handles \
       tests/unit/core/test_shopify_collection_fetch.py::test_fetch_collections_continues_after_http_error \
       -v
```

Expected: all three PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/app_integration/shopify/pipeline_service.py \
        tests/unit/core/test_shopify_collection_fetch.py
git commit -m "feat(shopify): add fetch_collections pipeline service step"
```

---

## Task 6: Wire `fetch_collections` into the Celery Chain

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py:221-235`

- [ ] **Step 1: Update the chain**

In `src/automana/worker/tasks/pipelines.py`, find `shopify_weekly_pipeline` and add the new step immediately after `start_run`:

```python
# Before:
    wf = chain(
        run_service.s(
            "ops.pipeline_services.start_run",
            pipeline_name="shopify_weekly",
            source_name="shopify",
            run_key=run_key,
            celery_task_id=self.request.id,
        ),
        run_service.s("shopify.pipeline.fetch_all_markets"),
        run_service.s("shopify.pipeline.process_to_parquet"),
        run_service.s("shopify.pipeline.stage_raw"),
        run_service.s("shopify.pipeline.promote_observations"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )

# After:
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

- [ ] **Step 2: Run the full unit test suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 3: Trigger the pipeline manually and monitor**

```bash
# From within the repo root, trigger the task directly via Celery
docker exec automana-celery-worker celery -A automana.worker.celery_app call \
  automana.worker.tasks.pipelines.shopify_weekly_pipeline
```

Then watch the pipeline steps:

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "SELECT ir.run_id, ir.status, ir.created_at,
          irs.step_name, irs.status AS step_status, irs.error_details
   FROM ops.ingestion_runs ir
   LEFT JOIN ops.ingestion_run_steps irs USING (run_id)
   WHERE ir.pipeline_name = 'shopify_weekly'
   ORDER BY ir.created_at DESC, irs.step_name
   LIMIT 20;"
```

- [ ] **Step 4: Verify collections were synced**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "SELECT market_id, COUNT(*) AS collection_count
   FROM markets.collection_handles
   GROUP BY market_id
   ORDER BY market_id;"
```

Expected: market_id 2 (GG Sydney) has > 0 rows.

- [ ] **Step 5: Verify price observations were promoted**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "SELECT COUNT(*) AS observations
   FROM pricing.price_observation po
   JOIN pricing.source_product sp ON sp.source_product_id = po.source_product_id
   WHERE sp.source_id = 1728;"
```

Expected: COUNT > 0 after a successful run.

- [ ] **Step 6: Commit**

```bash
git add src/automana/worker/tasks/pipelines.py
git commit -m "feat(shopify): prepend fetch_collections step to shopify_weekly_pipeline"
```

---

## Final Check

Run the complete unit suite one last time to confirm no regressions:

```bash
pytest tests/unit/ -v --tb=short
```

All tests should pass.
