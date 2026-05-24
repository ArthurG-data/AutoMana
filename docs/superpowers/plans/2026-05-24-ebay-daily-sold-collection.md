# eBay Daily Sold Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily category-wide eBay sweep plus JSON replay buffer to the watchlist scraper, giving full 24-hour sold-price coverage across US, AU, and CA markets.

**Architecture:** Two independent Celery tasks (category sweep at 09:00 AEST + enhanced watchlist at 09:45 AEST) both write raw items to `/data/ebay_raw/YYYY-MM-DD/{sweep|watchlist}/` before DB ingestion. On Celery retry, the task reads from disk instead of hitting the eBay API again. Both share a Redis quota guard capped at 4,500 calls/day. `promote_sold_obs` is unchanged and runs at 10:30 AEST once both staging writers are done.

**Tech Stack:** Python 3.12, asyncpg, redis.asyncio, EbayFindingAPIRepository (Finding API v1), Celery beat, pytest-asyncio, testcontainers

---

## File Map

| Action | Path |
|---|---|
| Modify | `src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py` |
| Modify | `src/automana/core/repositories/app_integration/ebay/sales_queries.py` |
| Modify | `src/automana/core/repositories/app_integration/ebay/sales_repository.py` |
| Create | `src/automana/core/services/app_integration/ebay/ebay_raw_io.py` |
| Create | `src/automana/core/services/app_integration/ebay/ebay_api_quota.py` |
| Create | `src/automana/core/services/app_integration/ebay/category_sweep_service.py` |
| Modify | `src/automana/core/services/app_integration/ebay/scrape_global_market_service.py` |
| Modify | `src/automana/worker/tasks/ebay.py` |
| Modify | `src/automana/worker/celeryconfig.py` |
| Create | `tests/unit/repositories/ebay/test_api_finding_pagination.py` |
| Create | `tests/unit/services/ebay/test_ebay_raw_io.py` |
| Create | `tests/integration/services/ebay/test_category_sweep.py` |
| Modify | `src/automana/worker/tasks/ebay.py` (cleanup task, done in Task 8) |
| Modify | `src/automana/worker/celeryconfig.py` (cleanup schedule, done in Task 8) |

---

### Task 1: Pagination in `find_completed_items`

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py`
- Create: `tests/unit/repositories/ebay/test_api_finding_pagination.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/repositories/ebay/test_api_finding_pagination.py`:

```python
"""Unit tests for EbayFindingAPIRepository pagination and keyword=None behaviour."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


async def test_pagination_collects_items_across_pages():
    """max_pages=2 should call _fetch_page twice and return combined items."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    page_responses = [
        ([{"item_id": "A", "title": "Card A", "price": 10.0, "currency": "USD",
           "condition": "Used", "url": None, "sold_date": "2026-05-24T10:00:00Z"}], 2),
        ([{"item_id": "B", "title": "Card B", "price": 12.0, "currency": "USD",
           "condition": "New", "url": None, "sold_date": "2026-05-24T11:00:00Z"}], 2),
    ]
    call_idx = 0

    async def fake_fetch_page(params):
        nonlocal call_idx
        result = page_responses[call_idx]
        call_idx += 1
        return result

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        items = await repo.find_completed_items("Sheoldred", "app-id", max_pages=5)

    assert len(items) == 2
    assert call_idx == 2  # stopped at total_pages=2, not max_pages=5


async def test_pagination_stops_early_on_empty_page():
    """If a page returns 0 items, no further pages are fetched."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    call_idx = 0

    async def fake_fetch_page(params):
        nonlocal call_idx
        call_idx += 1
        return ([], 10)  # 0 items but totalPages=10

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        items = await repo.find_completed_items("Sheoldred", "app-id", max_pages=5)

    assert items == []
    assert call_idx == 1  # stopped after first empty page


async def test_keywords_none_omits_param_from_request():
    """keywords=None must not include a 'keywords' key in the Finding API params."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    captured: dict = {}

    async def fake_fetch_page(params):
        captured.update(params)
        return ([], 1)

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        await repo.find_completed_items(None, "app-id")

    assert "keywords" not in captured


async def test_keywords_str_includes_param_in_request():
    """keywords='Sheoldred' must appear in the Finding API params."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    captured: dict = {}

    async def fake_fetch_page(params):
        captured.update(params)
        return ([], 1)

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        await repo.find_completed_items("Sheoldred", "app-id")

    assert captured.get("keywords") == "Sheoldred"


async def test_on_page_fetched_called_once_per_page():
    """on_page_fetched callback is invoked exactly once per successfully fetched page."""
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
        EbayFindingAPIRepository,
    )

    repo = EbayFindingAPIRepository(environment="production")
    page_responses = [
        ([{"item_id": "A", "title": "Card A", "price": 10.0, "currency": "USD",
           "condition": "Used", "url": None, "sold_date": "2026-05-24T10:00:00Z"}], 2),
        ([{"item_id": "B", "title": "Card B", "price": 12.0, "currency": "USD",
           "condition": "New", "url": None, "sold_date": "2026-05-24T11:00:00Z"}], 2),
    ]
    call_idx = 0

    async def fake_fetch_page(params):
        nonlocal call_idx
        result = page_responses[call_idx]
        call_idx += 1
        return result

    callback_count = 0

    async def on_page():
        nonlocal callback_count
        callback_count += 1

    with patch.object(repo, "_fetch_page", side_effect=fake_fetch_page):
        await repo.find_completed_items("Sheoldred", "app-id", max_pages=5, on_page_fetched=on_page)

    assert callback_count == 2, f"Expected 2 callbacks (one per page), got {callback_count}"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/arthur/projects/AutoMana
python -m pytest tests/unit/repositories/ebay/test_api_finding_pagination.py -v 2>&1 | head -40
```

Expected: ImportError or AttributeError — `_fetch_page` does not exist yet.

- [ ] **Step 3: Implement pagination in `ApiFinding_repository.py`**

Replace the existing `find_completed_items` method and add `_fetch_page`. The full file diff:

```python
# In EbayFindingAPIRepository — replace find_completed_items and add _fetch_page

    async def _fetch_page(self, params: dict) -> tuple[list[dict], int]:
        """Fetch one Finding API page. Returns (items, total_pages). Empty on rate-limit exhaustion."""
        for attempt in range(_MAX_RATE_LIMIT_RETRIES):
            async with self:
                response = await self.send("GET", _FINDING_ENDPOINT, params=params)
                data = self._parse_response(response)

            if _is_rate_limited(data):
                wait = (2 ** attempt) + 5
                logger.warning(
                    "finding_api_rate_limited",
                    extra={"attempt": attempt + 1, "wait_seconds": wait},
                )
                if attempt < _MAX_RATE_LIMIT_RETRIES - 1:
                    await asyncio.sleep(wait)
                    continue
                return [], 0

            items = _parse_finding_items(data)
            try:
                result_block = data["findCompletedItemsResponse"][0]
                pagination = result_block.get("paginationOutput", [{}])[0]
                total_pages = int(pagination.get("totalPages", ["1"])[0])
            except (KeyError, IndexError, ValueError):
                total_pages = 1
            return items, total_pages

        return [], 0

    async def find_completed_items(
        self,
        keywords: Optional[str],
        app_id: str,
        *,
        global_id: str = "EBAY-US",
        category_id: int = 2536,
        condition_id: Optional[int] = None,
        min_date: Optional[datetime] = None,
        limit: int = 100,
        max_pages: int = 1,
        on_page_fetched: Optional[Callable] = None,  # async callback fired once per page
    ) -> list[dict]:
        params: dict[str, Any] = {
            "OPERATION-NAME": "findCompletedItems",
            "SERVICE-VERSION": _SERVICE_VERSION,
            "SECURITY-APPNAME": app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "GLOBAL-ID": global_id,
            "categoryId": str(category_id),
            "itemFilter(0).name": "SoldItemsOnly",
            "itemFilter(0).value": "true",
            "paginationInput.entriesPerPage": str(min(limit, 100)),
        }

        if keywords is not None:
            params["keywords"] = keywords

        filter_idx = 1
        if condition_id is not None:
            params[f"itemFilter({filter_idx}).name"] = "Condition"
            params[f"itemFilter({filter_idx}).value"] = str(condition_id)
            filter_idx += 1

        if min_date is not None:
            if min_date.tzinfo is None:
                raise ValueError("min_date must be timezone-aware (UTC)")
            utc_date = min_date.astimezone(timezone.utc)
            params[f"itemFilter({filter_idx}).name"] = "EndTimeFrom"
            params[f"itemFilter({filter_idx}).value"] = utc_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        logger.info(
            "Finding API request",
            extra={"keywords": keywords, "category_id": category_id, "limit": limit, "max_pages": max_pages},
        )

        all_items: list[dict] = []
        for page in range(1, max_pages + 1):
            params["paginationInput.pageNumber"] = str(page)
            items, total_pages = await self._fetch_page(params)
            all_items.extend(items)
            if items and on_page_fetched is not None:
                await on_page_fetched()  # one increment per actual API call
            if not items or page >= total_pages:
                break

        return all_items
```

Apply the change — replace the existing `find_completed_items` block in `ApiFinding_repository.py`. Also add `Callable` to the `typing` import at the top of the file if not already present:
`from typing import Any, Callable, Optional`. The `_parse_finding_items` and `_is_rate_limited` module-level functions stay unchanged.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/unit/repositories/ebay/test_api_finding_pagination.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py \
        tests/unit/repositories/ebay/test_api_finding_pagination.py
git commit -m "feat(ebay): paginate find_completed_items; accept keywords=None for category sweep"
```

---

### Task 2: `get_ebay_card_lookup()` DB method

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/sales_queries.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/sales_repository.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/repositories/ebay/test_sales_repository_lookup.py`:

```python
"""Unit test: EbaySalesRepository.get_ebay_card_lookup delegates to execute_query."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


async def test_get_ebay_card_lookup_returns_dicts():
    from automana.core.repositories.app_integration.ebay.sales_repository import (
        EbaySalesRepository,
    )
    from automana.core.repositories.app_integration.ebay import sales_queries

    mock_conn = AsyncMock()
    repo = EbaySalesRepository(mock_conn)

    fake_rows = [
        {"source_product_id": 1, "card_name": "Sheoldred, the Apocalypse",
         "set_code": "DMU", "source_code": "ebay"},
        {"source_product_id": 2, "card_name": "Atraxa, Praetors' Voice",
         "set_code": "ONE", "source_code": "ebay"},
    ]

    with patch.object(repo, "execute_query", return_value=fake_rows) as mock_eq:
        result = await repo.get_ebay_card_lookup()

    mock_eq.assert_called_once_with(sales_queries.GET_EBAY_CARD_LOOKUP, ())
    assert len(result) == 2
    assert result[0]["card_name"] == "Sheoldred, the Apocalypse"
    assert result[1]["set_code"] == "ONE"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/unit/repositories/ebay/test_sales_repository_lookup.py -v
```

Expected: AttributeError — `GET_EBAY_CARD_LOOKUP` not in `sales_queries`.

- [ ] **Step 3: Add the SQL constant to `sales_queries.py`**

Append to `src/automana/core/repositories/app_integration/ebay/sales_queries.py`:

```python
GET_EBAY_CARD_LOOKUP = """
SELECT sp.source_product_id,
       ucr.card_name,
       cs.set_code,
       ps.code          AS source_code
FROM   pricing.source_product sp
JOIN   pricing.price_source ps       ON sp.source_id    = ps.source_id
JOIN   pricing.mtg_card_products mcp ON sp.product_id   = mcp.product_id
JOIN   card_catalog.card_version cv  ON mcp.card_version_id = cv.card_version_id
JOIN   card_catalog.unique_cards_ref ucr ON cv.unique_card_id = ucr.unique_card_id
JOIN   card_catalog.sets cs          ON cv.set_id        = cs.set_id
WHERE  ps.code = 'ebay'
ORDER  BY sp.source_product_id;
"""
```

- [ ] **Step 4: Add the method to `EbaySalesRepository`**

Add after the `get_listing_meta` method (before the final `list_local_sales`):

```python
    async def get_ebay_card_lookup(self) -> list[dict]:
        """Return all eBay source_products with card metadata for title-matching."""
        rows = await self.execute_query(sales_queries.GET_EBAY_CARD_LOOKUP, ())
        return [dict(r) for r in rows]
```

- [ ] **Step 5: Run test to confirm it passes**

```bash
python -m pytest tests/unit/repositories/ebay/test_sales_repository_lookup.py -v
```

Expected: 1 test PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/sales_queries.py \
        src/automana/core/repositories/app_integration/ebay/sales_repository.py \
        tests/unit/repositories/ebay/test_sales_repository_lookup.py
git commit -m "feat(ebay): add get_ebay_card_lookup() for category sweep card matching"
```

---

### Task 3: Shared utilities — JSON IO and Redis quota guard

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/ebay_raw_io.py`
- Create: `src/automana/core/services/app_integration/ebay/ebay_api_quota.py`
- Create: `tests/unit/services/ebay/test_ebay_raw_io.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/services/ebay/test_ebay_raw_io.py`:

```python
"""Unit tests for JSON staging IO helpers."""
from __future__ import annotations

import json
import pytest
from pathlib import Path


def test_write_items_creates_file_with_correct_structure(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import write_items_to_json

    p = tmp_path / "EBAY-US.json"
    items = [{"item_id": "A1", "title": "Sheoldred DMU NM", "price": 18.99}]
    write_items_to_json(p, items, marketplace="EBAY-US", source_product_id=None)

    assert p.exists()
    data = json.loads(p.read_text())
    assert data["marketplace"] == "EBAY-US"
    assert data["source_product_id"] is None
    assert data["items"] == items
    assert "fetched_at" in data


def test_write_items_creates_parent_dirs(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import write_items_to_json

    p = tmp_path / "deep" / "nested" / "file.json"
    write_items_to_json(p, [], marketplace="EBAY-AU", source_product_id=999)
    assert p.exists()


def test_load_items_returns_list(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import (
        load_items_from_json,
        write_items_to_json,
    )

    p = tmp_path / "test.json"
    items = [{"item_id": "B1", "title": "Atraxa ONE", "price": 5.0}]
    write_items_to_json(p, items, marketplace="EBAY-US", source_product_id=42)
    result = load_items_from_json(p)
    assert result == items


def test_load_items_raises_on_corrupt_json(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import load_items_from_json

    p = tmp_path / "bad.json"
    p.write_text("not-valid-json{{")
    with pytest.raises(ValueError, match="Corrupt"):
        load_items_from_json(p)


def test_load_items_raises_on_missing_items_key(tmp_path):
    from automana.core.services.app_integration.ebay.ebay_raw_io import load_items_from_json

    p = tmp_path / "missing_key.json"
    p.write_text(json.dumps({"marketplace": "EBAY-US"}))
    with pytest.raises(ValueError, match="Corrupt"):
        load_items_from_json(p)


def test_sweep_path_structure(tmp_path, monkeypatch):
    from automana.core.services.app_integration.ebay import ebay_raw_io

    monkeypatch.setattr(ebay_raw_io, "get_ebay_raw_dir", lambda: tmp_path)
    from automana.core.services.app_integration.ebay.ebay_raw_io import sweep_path

    p = sweep_path("2026-05-24", "EBAY-US")
    assert p == tmp_path / "2026-05-24" / "sweep" / "EBAY-US.json"


def test_watchlist_path_structure(tmp_path, monkeypatch):
    from automana.core.services.app_integration.ebay import ebay_raw_io

    monkeypatch.setattr(ebay_raw_io, "get_ebay_raw_dir", lambda: tmp_path)
    from automana.core.services.app_integration.ebay.ebay_raw_io import watchlist_path

    p = watchlist_path("2026-05-24", 12060647, "EBAY-AU")
    assert p == tmp_path / "2026-05-24" / "watchlist" / "12060647_EBAY-AU.json"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/unit/services/ebay/test_ebay_raw_io.py -v 2>&1 | head -20
```

Expected: ModuleNotFoundError — `ebay_raw_io` does not exist.

- [ ] **Step 3: Create `ebay_raw_io.py`**

Create `src/automana/core/services/app_integration/ebay/ebay_raw_io.py`:

```python
"""JSON staging helpers for eBay raw API responses (sweep + watchlist replay buffer)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_SWEEP_SUBDIR = "sweep"
_WATCHLIST_SUBDIR = "watchlist"


def get_ebay_raw_dir() -> Path:
    settings = get_settings()
    return Path(getattr(settings, "data_dir", "/data")) / "ebay_raw"


def sweep_path(today: str, marketplace: str) -> Path:
    return get_ebay_raw_dir() / today / _SWEEP_SUBDIR / f"{marketplace}.json"


def watchlist_path(today: str, source_product_id: int, marketplace: str) -> Path:
    return get_ebay_raw_dir() / today / _WATCHLIST_SUBDIR / f"{source_product_id}_{marketplace}.json"


def load_items_from_json(path: Path) -> list[dict]:
    """Load items list from a staged JSON file. Raises ValueError if corrupt or missing 'items' key."""
    try:
        data = json.loads(path.read_text())
        return data["items"]
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        raise ValueError(f"Corrupt or unreadable replay file: {path}") from exc


def write_items_to_json(
    path: Path,
    items: list[dict],
    marketplace: str,
    source_product_id: Optional[int] = None,
) -> None:
    """Write API items to a staged JSON file. Creates parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "marketplace": marketplace,
        "source_product_id": source_product_id,
        "items": items,
    }
    path.write_text(json.dumps(payload, default=str))
```

- [ ] **Step 4: Create `ebay_api_quota.py`**

Create `src/automana/core/services/app_integration/ebay/ebay_api_quota.py`:

```python
"""Redis-backed daily API call quota guard shared across eBay Finding API tasks.

Tracks one unit per find_completed_items() invocation.
Key: ebay:api_calls:{YYYY-MM-DD}, expires after 24 h.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_QUOTA_KEY_PREFIX = "ebay:api_calls"
_KEY_TTL_SECONDS = 86_400


def _key(today: str) -> str:
    return f"{_QUOTA_KEY_PREFIX}:{today}"


async def quota_remaining(redis_client, today: str, limit: int) -> int:
    """Return how many API calls remain for today (0 = exhausted)."""
    raw = await redis_client.get(_key(today))
    used = int(raw) if raw else 0
    return max(0, limit - used)


async def quota_increment(redis_client, today: str) -> int:
    """Increment daily call counter. Returns new count. Sets TTL on first use."""
    key = _key(today)
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, _KEY_TTL_SECONDS)
    return count
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python -m pytest tests/unit/services/ebay/test_ebay_raw_io.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/ebay_raw_io.py \
        src/automana/core/services/app_integration/ebay/ebay_api_quota.py \
        tests/unit/services/ebay/test_ebay_raw_io.py
git commit -m "feat(ebay): add JSON staging IO helpers and Redis API quota guard"
```

---

### Task 4: `EbayCategorySweepService`

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/category_sweep_service.py`

- [ ] **Step 1: Write the unit test for `_match_item`**

Add to a new file `tests/unit/services/ebay/test_category_sweep_service.py`:

```python
"""Unit tests for EbayCategorySweepService internal matching logic."""
from __future__ import annotations

import pytest


def _make_lookup(spid, card_name, set_code="DMU"):
    return {spid: {"source_product_id": spid, "card_name": card_name, "set_code": set_code}}


def test_match_item_returns_best_scoring_card():
    from automana.core.services.app_integration.ebay.category_sweep_service import _match_item

    lookup = {}
    lookup.update(_make_lookup(1, "Sheoldred, the Apocalypse", "DMU"))
    lookup.update(_make_lookup(2, "Atraxa, Praetors' Voice", "ONE"))

    item = {"item_id": "X", "title": "Sheoldred the Apocalypse DMU NM MTG", "price": 18.99, "currency": "USD"}
    spid, score, card = _match_item(item, lookup)

    assert spid == 1
    assert score >= 0.5
    assert card["card_name"] == "Sheoldred, the Apocalypse"


def test_match_item_returns_none_below_threshold():
    from automana.core.services.app_integration.ebay.category_sweep_service import _match_item

    lookup = _make_lookup(1, "Sheoldred, the Apocalypse", "DMU")
    item = {"item_id": "Y", "title": "MTG lot 50 random cards mixed", "price": 5.0}
    spid, score, card = _match_item(item, lookup)

    assert spid is None


def test_match_item_empty_lookup_returns_none():
    from automana.core.services.app_integration.ebay.category_sweep_service import _match_item

    spid, score, card = _match_item({"title": "Sheoldred DMU"}, {})
    assert spid is None
    assert card is None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/unit/services/ebay/test_category_sweep_service.py -v 2>&1 | head -20
```

Expected: ModuleNotFoundError — `category_sweep_service` does not exist.

- [ ] **Step 3: Create `category_sweep_service.py`**

Create `src/automana/core/services/app_integration/ebay/category_sweep_service.py`:

```python
"""eBay daily category-wide sweep — fetch all MTG sold listings, match to known cards."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis

from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
)
from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)
from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay.market_price_scorer import score_title
from automana.core.services.app_integration.ebay.title_parser import (
    CONDITION_ID_MAP,
    FINISH_ID_MAP,
    parse_condition_code,
    parse_finish_code,
)
from automana.core.services.app_integration.ebay.ebay_raw_io import (
    sweep_path,
    load_items_from_json,
    write_items_to_json,
)
from automana.core.services.app_integration.ebay.ebay_api_quota import (
    quota_remaining,
    quota_increment,
)
from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_MARKETPLACES = ("EBAY-US", "EBAY-AU", "EBAY-ENCA")
_DEFAULT_LANGUAGE_ID = 1
_SCORE_THRESHOLD = 0.5
_SWEEP_MAX_PAGES = 100
_INTER_MARKETPLACE_DELAY = 2.0
_API_QUOTA_LIMIT = 4_500


@ServiceRegistry.register(
    path="integrations.ebay.category_sweep",
    db_repositories=["ebay_sales", "ebay_scrape"],
    api_repositories=["ebay_finding"],
    runs_in_transaction=False,
)
async def ebay_category_sweep(
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    **kwargs: Any,
) -> dict:
    """Daily category sweep: fetch all MTG sold items, title-match to known eBay cards."""
    settings = get_settings()
    app_id = getattr(settings, "ebay_app_id", None)
    if not app_id:
        logger.warning("ebay_category_sweep_no_app_id")
        return {"fetched": 0, "matched": 0, "inserted": 0}

    lookup_rows = await ebay_sales_repository.get_ebay_card_lookup()
    if not lookup_rows:
        logger.info("ebay_category_sweep_no_cards_in_lookup")
        return {"fetched": 0, "matched": 0, "inserted": 0}

    card_lookup: dict[int, dict] = {r["source_product_id"]: r for r in lookup_rows}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    redis_host = getattr(settings, "redis_host", "localhost")
    redis_port = getattr(settings, "redis_port", 6379)
    redis_client = aioredis.from_url(f"redis://{redis_host}:{redis_port}/0")

    totals = {"fetched": 0, "matched": 0, "inserted": 0}
    try:
        for marketplace in _MARKETPLACES:
            result = await _sweep_marketplace(
                marketplace=marketplace,
                today=today,
                app_id=app_id,
                card_lookup=card_lookup,
                ebay_finding_repository=ebay_finding_repository,
                ebay_scrape_repository=ebay_scrape_repository,
                redis_client=redis_client,
            )
            for k in totals:
                totals[k] += result[k]
            await asyncio.sleep(_INTER_MARKETPLACE_DELAY)
    finally:
        await redis_client.aclose()

    logger.info("ebay_category_sweep_complete", extra=totals)
    return totals


async def _sweep_marketplace(
    marketplace: str,
    today: str,
    app_id: str,
    card_lookup: dict[int, dict],
    ebay_finding_repository: EbayFindingAPIRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    redis_client,
) -> dict:
    path = sweep_path(today, marketplace)

    if path.exists():
        try:
            items = load_items_from_json(path)
            logger.info(
                "ebay_category_sweep_replay",
                extra={"marketplace": marketplace, "items": len(items)},
            )
        except ValueError:
            logger.warning(
                "ebay_category_sweep_corrupt_file", extra={"path": str(path)}
            )
            path.unlink(missing_ok=True)
            items = await _fetch_and_stage(
                path, marketplace, app_id, ebay_finding_repository, redis_client, today
            )
    else:
        items = await _fetch_and_stage(
            path, marketplace, app_id, ebay_finding_repository, redis_client, today
        )

    fetched = len(items)
    matched = 0
    inserted = 0

    for item in items:
        best_spid, best_score, best_card = _match_item(item, card_lookup)
        if best_spid is None:
            continue
        matched += 1
        ok = await _insert_matched(item, best_spid, marketplace, ebay_scrape_repository)
        if ok:
            inserted += 1

    logger.info(
        "ebay_category_sweep_marketplace_done",
        extra={
            "marketplace": marketplace,
            "fetched": fetched,
            "matched": matched,
            "inserted": inserted,
        },
    )
    return {"fetched": fetched, "matched": matched, "inserted": inserted}


async def _fetch_and_stage(path, marketplace, app_id, finding_repo, redis_client, today) -> list[dict]:
    if await quota_remaining(redis_client, today, _API_QUOTA_LIMIT) == 0:
        logger.warning(
            "ebay_category_sweep_quota_exhausted",
            extra={"marketplace": marketplace, "today": today},
        )
        return []

    async def _on_page():
        await quota_increment(redis_client, today)

    items = await finding_repo.find_completed_items(
        keywords=None,
        app_id=app_id,
        global_id=marketplace,
        max_pages=_SWEEP_MAX_PAGES,
        on_page_fetched=_on_page,  # one Redis increment per fetched page
    )

    try:
        write_items_to_json(path, items, marketplace, source_product_id=None)
    except OSError:
        logger.error("ebay_category_sweep_write_failed", extra={"path": str(path)})

    return items


def _match_item(
    item: dict, card_lookup: dict[int, dict]
) -> tuple[Optional[int], float, Optional[dict]]:
    title = item.get("title", "")
    best_spid: Optional[int] = None
    best_score = 0.0
    best_card: Optional[dict] = None

    for spid, card in card_lookup.items():
        sc = score_title(
            title, card["card_name"], card.get("set_code"), is_foil=None, frame=None
        )
        if sc > best_score:
            best_score = sc
            best_spid = spid
            best_card = card

    if best_score < _SCORE_THRESHOLD:
        return None, best_score, None
    return best_spid, best_score, best_card


async def _insert_matched(
    item: dict,
    source_product_id: int,
    marketplace: str,
    ebay_scrape_repository: EbayScrapeSoldRepository,
) -> bool:
    item_id = item.get("item_id", "")
    title = item.get("title", "")
    sold_date = item.get("sold_date")
    price_raw = item.get("price")

    if not item_id or not sold_date or price_raw is None:
        return False

    try:
        price_cents = round(float(price_raw) * 100)
    except (TypeError, ValueError):
        return False

    try:
        sold_at = datetime.fromisoformat(sold_date.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        sold_at = datetime.now(timezone.utc)

    finish_code = parse_finish_code(title)
    condition_code = parse_condition_code(item.get("condition"), title)

    try:
        await ebay_scrape_repository.insert_scraped_sold(
            item_id=item_id,
            title=title,
            source_product_id=source_product_id,
            price_cents=price_cents,
            currency=item.get("currency", "USD"),
            marketplace_id=marketplace,
            condition_id=CONDITION_ID_MAP.get(condition_code, 1),
            finish_id=FINISH_ID_MAP.get(finish_code, 1),
            language_id=_DEFAULT_LANGUAGE_ID,
            sold_at=sold_at,
        )
        return True
    except Exception:
        logger.warning(
            "ebay_category_sweep_insert_failed", extra={"item_id": item_id}
        )
        return False
```

- [ ] **Step 4: Run unit tests to confirm they pass**

```bash
python -m pytest tests/unit/services/ebay/test_category_sweep_service.py -v
```

Expected: 3 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/category_sweep_service.py \
        tests/unit/services/ebay/test_category_sweep_service.py
git commit -m "feat(ebay): add EbayCategorySweepService with JSON replay and Redis quota guard"
```

---

### Task 5: JSON replay buffer in `scrape_global_market_service`

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/scrape_global_market_service.py`

- [ ] **Step 1: Plan the changes**

Two additions to the existing file:
1. At the top of `scrape_global_market`, compute `today` and pass it to `_scrape_one_card`.
2. In `_scrape_one_card`, check for the watchlist JSON before calling `find_completed_items`, write after, use `max_pages=3`.

No changes to scoring, filtering, or DB insertion logic.

- [ ] **Step 2: Add imports and `today` to `scrape_global_market`**

At the top of `scrape_global_market_service.py`, add to the import block:

```python
from automana.core.services.app_integration.ebay.ebay_raw_io import (
    watchlist_path,
    load_items_from_json,
    write_items_to_json,
)
from automana.core.services.app_integration.ebay.ebay_api_quota import (
    quota_remaining,
    quota_increment,
)
import redis.asyncio as aioredis
```

In `scrape_global_market`, after `min_date = ...`, add:

```python
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    redis_host = getattr(settings, "redis_host", "localhost")
    redis_port = getattr(settings, "redis_port", 6379)
    redis_client = aioredis.from_url(f"redis://{redis_host}:{redis_port}/0")
```

Wrap the outer loop in a try/finally to close the Redis client:

```python
    try:
        for card_version_id in targets:
            # ... existing loop body unchanged, but _scrape_one_card call gains today= and redis_client=
    finally:
        await redis_client.aclose()
```

Update the `_scrape_one_card` call inside the loop to pass `today` and `redis_client`:

```python
                count = await _scrape_one_card(
                    card_version_id=card_version_id,
                    card=card,
                    app_id=app_id,
                    marketplace=marketplace,
                    min_date=min_date,
                    limit_per_card=limit_per_card,
                    score_threshold=score_threshold,
                    ebay_sales_repository=ebay_sales_repository,
                    ebay_scrape_repository=ebay_scrape_repository,
                    ebay_finding_repository=ebay_finding_repository,
                    source_product_id=source_product_id,
                    today=today,
                    redis_client=redis_client,
                )
```

- [ ] **Step 3: Modify `_scrape_one_card` signature and add JSON staging**

Add `today: str` and `redis_client` parameters to `_scrape_one_card`:

```python
async def _scrape_one_card(
    card_version_id: UUID,
    card: dict,
    app_id: str,
    marketplace: str,
    min_date: datetime,
    limit_per_card: int,
    score_threshold: float,
    ebay_sales_repository: EbaySalesRepository,
    ebay_scrape_repository: EbayScrapeSoldRepository,
    ebay_finding_repository: EbayFindingAPIRepository,
    source_product_id: int,
    today: str,
    redis_client,
) -> int:
```

Replace the `items = await ebay_finding_repository.find_completed_items(...)` block with:

```python
    json_path = watchlist_path(today, source_product_id, marketplace)

    if json_path.exists():
        try:
            items = load_items_from_json(json_path)
            logger.info(
                "scrape_global_market_replay",
                extra={"source_product_id": source_product_id, "marketplace": marketplace},
            )
        except ValueError:
            logger.warning(
                "scrape_global_market_corrupt_watchlist_file",
                extra={"path": str(json_path)},
            )
            json_path.unlink(missing_ok=True)
            items = await _fetch_watchlist_items(
                keywords, app_id, marketplace, min_date, limit_per_card,
                ebay_finding_repository, json_path, source_product_id, redis_client, today,
            )
    else:
        items = await _fetch_watchlist_items(
            keywords, app_id, marketplace, min_date, limit_per_card,
            ebay_finding_repository, json_path, source_product_id, redis_client, today,
        )
```

Add the helper function `_fetch_watchlist_items` below `_scrape_one_card`:

```python
async def _fetch_watchlist_items(
    keywords: str,
    app_id: str,
    marketplace: str,
    min_date: datetime,
    limit_per_card: int,
    ebay_finding_repository: EbayFindingAPIRepository,
    json_path,
    source_product_id: int,
    redis_client,
    today: str,
) -> list[dict]:
    if await quota_remaining(redis_client, today, _API_DAILY_BUDGET) == 0:
        logger.warning(
            "scrape_global_market_quota_exhausted",
            extra={"source_product_id": source_product_id, "marketplace": marketplace},
        )
        return []

    async def _on_page():
        await quota_increment(redis_client, today)

    items = await ebay_finding_repository.find_completed_items(
        keywords=keywords,
        app_id=app_id,
        global_id=marketplace,
        min_date=min_date,
        limit=limit_per_card,
        max_pages=3,
        on_page_fetched=_on_page,  # one Redis increment per fetched page
    )

    try:
        write_items_to_json(json_path, items, marketplace, source_product_id=source_product_id)
    except OSError:
        logger.error(
            "scrape_global_market_watchlist_write_failed", extra={"path": str(json_path)}
        )
    return items
```

Note: the existing in-memory `api_calls` counter and `warn_at` / budget guard logic in `scrape_global_market` can be removed since the Redis quota guard now handles this. Remove the `api_calls += 1`, `warn_at`, `_API_WARN_THRESHOLD`, and the `api_calls >= _API_DAILY_BUDGET` check from the outer loop in `scrape_global_market`. Keep `_API_DAILY_BUDGET` as the constant used by the quota guard.

- [ ] **Step 4: Run the existing integration test to confirm no regression**

```bash
python -m pytest tests/integration/services/ebay/test_promote_sold_obs.py::test_staged_row_is_promoted_to_price_observation -v
```

Expected: PASSED — this test doesn't touch `scrape_global_market_service` so it confirms the DB layer is intact.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/scrape_global_market_service.py
git commit -m "feat(ebay): add JSON replay buffer and max_pages=3 to watchlist scraper"
```

---

### Task 6: Celery wiring — new task and schedule shifts

**Files:**
- Modify: `src/automana/worker/tasks/ebay.py`
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 1: Add the new Celery task to `tasks/ebay.py`**

Add at the top of the imports block:

```python
import automana.core.services.app_integration.ebay.category_sweep_service  # noqa: F401
```

Append the new task after the existing `ebay_scrape_external_sold_task`:

```python
@app.task(
    name="automana.worker.tasks.ebay.ebay_category_sweep_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def ebay_category_sweep_task(self):
    """Daily category-wide eBay sold sweep across EBAY-US, EBAY-AU, EBAY-ENCA."""
    state = get_state()
    set_task_id(self.request.id)
    set_service_path("integrations.ebay.category_sweep")
    if not state.initialized:
        init_backend_runtime()
    try:
        result = state.loop.run_until_complete(
            ServiceManager.execute_service("integrations.ebay.category_sweep")
        )
        logger.info("ebay_category_sweep_task_complete", extra={"result": result})
        return result
    except Exception:
        logger.exception("ebay_category_sweep_task_failed")
        raise
    finally:
        set_service_path(None)
        set_task_id(None)
```

- [ ] **Step 2: Update `celeryconfig.py` schedule**

Apply these changes to the `beat_schedule` dict:

**Add** (new entry):
```python
    "ebay-category-sweep-daily": {
        "task": "automana.worker.tasks.ebay.ebay_category_sweep_task",
        "schedule": crontab(hour=9, minute=0),   # 09:00 AEST
    },
```

**Modify** `ebay-scrape-external-sold-nightly` — shift from 07:15 to 09:45:
```python
    "ebay-scrape-external-sold-nightly": {
        "task": "automana.worker.tasks.ebay.ebay_scrape_external_sold_task",
        "schedule": crontab(hour=9, minute=45),  # 09:45 AEST (was 07:15)
    },
```

**Modify** `ebay-promote-sold-obs-nightly` — shift from 08:00 to 10:30:
```python
    "ebay-promote-sold-obs-nightly": {
        "task": "run_service",
        "schedule": crontab(hour=10, minute=30),   # 10:30 AEST (was 08:00)
        "kwargs": {"path": "integrations.ebay.promote_sold_obs"},
    },
```

- [ ] **Step 3: Verify the Celery config imports cleanly**

```bash
cd /home/arthur/projects/AutoMana
python -c "from automana.worker import celeryconfig; print('OK')"
```

Expected: `OK`

```bash
python -c "from automana.worker.tasks.ebay import ebay_category_sweep_task; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/automana/worker/tasks/ebay.py \
        src/automana/worker/celeryconfig.py
git commit -m "feat(ebay): add ebay_category_sweep_task; shift scrape to 09:45, promote to 10:30 AEST"
```

---

### Task 7: Integration tests

**Files:**
- Create: `tests/integration/services/ebay/test_category_sweep.py`

- [ ] **Step 1: Write the tests**

Create `tests/integration/services/ebay/test_category_sweep.py`:

```python
"""Integration tests for the eBay category sweep pipeline.

test_category_sweep_ingest:
    Seeds 2 matchable eBay source_products + writes a synthetic sweep JSON.
    Runs EbayCategorySweepService in replay mode (no network).
    Asserts: 2 rows in ebay_scraped_sold, noise item skipped.

test_watchlist_pagination_ingest:
    Seeds 1 source_product + writes a 150-item synthetic watchlist JSON.
    Runs scrape_global_market_service._scrape_one_card in replay mode.
    Asserts: 150 rows inserted, no duplicate item_ids.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration]

_YESTERDAY = datetime.now(timezone.utc) - timedelta(days=1)


# ── helpers ────────────────────────────────────────────────────────────────

def _make_sweep_item(item_id: str, title: str, price: float = 10.0) -> dict:
    return {
        "item_id": item_id,
        "title": title,
        "price": price,
        "currency": "USD",
        "condition": "Used",
        "url": None,
        "sold_date": _YESTERDAY.isoformat(),
    }


def _write_sweep_json(base_dir: Path, marketplace: str, items: list[dict]) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = base_dir / today / "sweep" / f"{marketplace}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "marketplace": marketplace,
        "source_product_id": None,
        "items": items,
    }
    path.write_text(json.dumps(payload))
    return path


def _write_watchlist_json(base_dir: Path, spid: int, marketplace: str, items: list[dict]) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = base_dir / today / "watchlist" / f"{spid}_{marketplace}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "marketplace": marketplace,
        "source_product_id": spid,
        "items": items,
    }
    path.write_text(json.dumps(payload))
    return path


# ── fixtures ───────────────────────────────────────────────────────────────

async def _seed_extra_source_product(conn, seeded_db: dict) -> int:
    """Seed a second eBay card (Atraxa ONE) sharing the same FK spine."""
    set_type_id = await conn.fetchval(
        "INSERT INTO card_catalog.set_type_list_ref (set_type) VALUES ('expansion') "
        "ON CONFLICT (set_type) DO UPDATE SET set_type = EXCLUDED.set_type RETURNING set_type_id"
    )
    rarity_id = await conn.fetchval(
        "INSERT INTO card_catalog.rarities_ref (rarity_name) VALUES ('mythic') "
        "ON CONFLICT (rarity_name) DO UPDATE SET rarity_name = EXCLUDED.rarity_name RETURNING rarity_id"
    )
    border_id = await conn.fetchval(
        "INSERT INTO card_catalog.border_color_ref (border_color_name) VALUES ('black') "
        "ON CONFLICT (border_color_name) DO UPDATE SET border_color_name = EXCLUDED.border_color_name RETURNING border_color_id"
    )
    frame_id = await conn.fetchval(
        "INSERT INTO card_catalog.frames_ref (frame_year) VALUES ('2015') "
        "ON CONFLICT (frame_year) DO UPDATE SET frame_year = EXCLUDED.frame_year RETURNING frame_id"
    )
    layout_id = await conn.fetchval(
        "INSERT INTO card_catalog.layouts_ref (layout_name) VALUES ('normal') "
        "ON CONFLICT (layout_name) DO UPDATE SET layout_name = EXCLUDED.layout_name RETURNING layout_id"
    )
    unique_card_id = await conn.fetchval(
        "INSERT INTO card_catalog.unique_cards_ref (card_name) VALUES ($1) RETURNING unique_card_id",
        f"Atraxa, Praetors' Voice [{uuid.uuid4().hex[:6].upper()}]",
    )
    set_code = "ONE" + uuid.uuid4().hex[:4].upper()
    set_id = await conn.fetchval(
        "INSERT INTO card_catalog.sets (set_name, set_code, set_type_id, released_at) "
        "VALUES ($1, $2, $3, '2023-02-10') RETURNING set_id",
        f"Phyrexia All Will Be One [{set_code}]", set_code, set_type_id,
    )
    card_version_id = await conn.fetchval(
        "INSERT INTO card_catalog.card_version "
        "(unique_card_id, set_id, collector_number, rarity_id, border_color_id, frame_id, layout_id) "
        "VALUES ($1, $2, '10', $3, $4, $5, $6) RETURNING card_version_id",
        unique_card_id, set_id, rarity_id, border_id, frame_id, layout_id,
    )
    game_id = await conn.fetchval("SELECT game_id FROM card_catalog.card_games_ref WHERE code = 'mtg'")
    product_id = await conn.fetchval(
        "INSERT INTO pricing.product_ref (game_id) VALUES ($1) RETURNING product_id", game_id
    )
    await conn.execute(
        "INSERT INTO pricing.mtg_card_products (product_id, card_version_id) VALUES ($1, $2)",
        product_id, card_version_id,
    )
    ebay_source_id = await conn.fetchval("SELECT source_id FROM pricing.price_source WHERE code = 'ebay'")
    source_product_id = await conn.fetchval(
        "INSERT INTO pricing.source_product (product_id, source_id) VALUES ($1, $2) "
        "ON CONFLICT (product_id, source_id) DO UPDATE SET product_id = EXCLUDED.product_id "
        "RETURNING source_product_id",
        product_id, ebay_source_id,
    )
    return source_product_id


# ── tests ──────────────────────────────────────────────────────────────────

async def test_category_sweep_ingest(db_pool, seeded_db, tmp_path):
    """Replay mode: 2 matching items inserted, 1 noise item skipped."""
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import EbayScrapeSoldRepository
    from automana.core.services.app_integration.ebay.category_sweep_service import ebay_category_sweep

    spid_1 = seeded_db["source_product_id"]

    async with db_pool.acquire() as conn:
        spid_2 = await _seed_extra_source_product(conn, seeded_db)

    # Build sweep JSON: 2 matching + 1 noise
    card_name_1 = seeded_db["card_name"]  # e.g. "Sheoldred, the Apocalypse [ABCDEF]"
    sweep_items = [
        _make_sweep_item("SWEEP-001", f"{card_name_1} NM MTG", price=18.99),
        _make_sweep_item("SWEEP-002", "Atraxa Praetors Voice ONE NM MTG", price=9.50),
        _make_sweep_item("SWEEP-003", "MTG lot 200 random bulk commons", price=5.00),
    ]
    _write_sweep_json(tmp_path, "EBAY-US", sweep_items)

    # Patch ebay_raw_dir to tmp_path so the service reads from our file
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.aclose = AsyncMock()

    import automana.core.services.app_integration.ebay.category_sweep_service as svc_mod

    with patch.object(svc_mod, "get_settings") as mock_settings, \
         patch("automana.core.services.app_integration.ebay.ebay_raw_io.get_ebay_raw_dir", return_value=tmp_path), \
         patch("automana.core.services.app_integration.ebay.category_sweep_service.aioredis") as mock_aioredis:
        mock_settings.return_value = MagicMock(ebay_app_id="test-app-id", redis_host="localhost", redis_port=6379)
        mock_aioredis.from_url.return_value = mock_redis

        # Only sweep EBAY-US to keep the test fast
        with patch.object(svc_mod, "_MARKETPLACES", ("EBAY-US",)):
            async with db_pool.acquire() as conn:
                result = await ebay_category_sweep(
                    ebay_sales_repository=EbaySalesRepository(conn),
                    ebay_scrape_repository=EbayScrapeSoldRepository(conn),
                    ebay_finding_repository=AsyncMock(),
                )

    assert result["fetched"] == 3
    assert result["matched"] == 2, f"Expected 2 matched, got {result['matched']}"
    assert result["inserted"] == 2, f"Expected 2 inserted, got {result['inserted']}"

    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM pricing.ebay_scraped_sold WHERE item_id = ANY($1::text[])",
            ["SWEEP-001", "SWEEP-002"],
        )
    assert count == 2, f"Expected 2 rows in ebay_scraped_sold, found {count}"

    # Cleanup
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.ebay_scraped_sold WHERE item_id = ANY($1::text[])",
            ["SWEEP-001", "SWEEP-002", "SWEEP-003"],
        )
        await conn.execute("DELETE FROM pricing.source_product WHERE source_product_id = $1", spid_2)


async def test_watchlist_pagination_ingest(db_pool, seeded_db, tmp_path):
    """Replay mode: 150-item watchlist JSON fully inserted with no duplicate item_ids."""
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import EbayScrapeSoldRepository
    from automana.core.services.app_integration.ebay.scrape_global_market_service import _scrape_one_card
    from automana.core.services.app_integration.ebay import scrape_global_market_service as svc_mod

    spid = seeded_db["source_product_id"]
    card_name = seeded_db["card_name"]

    watchlist_items = [
        {
            "item_id": f"WATCH-{i:04d}",
            "title": f"{card_name} NM MTG",
            "price": 18.99,
            "currency": "USD",
            "condition": "Used",
            "url": None,
            "sold_date": _YESTERDAY.isoformat(),
        }
        for i in range(150)
    ]
    _write_watchlist_json(tmp_path, spid, "EBAY-US", watchlist_items)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.aclose = AsyncMock()

    card = {
        "card_name": card_name,
        "set_code": "DMU",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }

    with patch("automana.core.services.app_integration.ebay.ebay_raw_io.get_ebay_raw_dir", return_value=tmp_path):
        async with db_pool.acquire() as conn:
            ebay_scrape = EbayScrapeSoldRepository(conn)
            count = await _scrape_one_card(
                card_version_id=seeded_db["card_version_id"],
                card=card,
                app_id="test-app-id",
                marketplace="EBAY-US",
                min_date=_YESTERDAY - timedelta(days=1),
                limit_per_card=100,
                score_threshold=0.5,
                ebay_sales_repository=AsyncMock(),
                ebay_scrape_repository=ebay_scrape,
                ebay_finding_repository=AsyncMock(),
                source_product_id=spid,
                today=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                redis_client=mock_redis,
            )

    assert count == 150, f"Expected 150 rows inserted, got {count}"

    async with db_pool.acquire() as conn:
        ids_in_db = await conn.fetch(
            "SELECT item_id FROM pricing.ebay_scraped_sold WHERE source_product_id = $1", spid
        )
    assert len(ids_in_db) == 150
    assert len({r["item_id"] for r in ids_in_db}) == 150, "Duplicate item_ids detected"

    # Cleanup
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.ebay_scraped_sold WHERE source_product_id = $1", spid
        )


@pytest.mark.live
@pytest.mark.skipif(
    not os.getenv("EBAY_APP_ID"),
    reason="EBAY_APP_ID not set — live eBay API test skipped",
)
async def test_live_category_sweep(db_pool, seeded_db, tmp_path):
    """Live smoke: real eBay category API call, at least 1 item matched and staged.

    Run with:
        EBAY_APP_ID=<your-app-id> pytest tests/integration/services/ebay/ -m "integration and live" -s
    """
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository
    from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import EbayScrapeSoldRepository
    from automana.core.repositories.app_integration.ebay.ApiFinding_repository import EbayFindingAPIRepository
    from automana.core.services.app_integration.ebay.category_sweep_service import ebay_category_sweep
    import automana.core.services.app_integration.ebay.category_sweep_service as svc_mod

    app_id = os.environ["EBAY_APP_ID"]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with patch.object(svc_mod, "get_settings") as mock_settings, \
         patch("automana.core.services.app_integration.ebay.ebay_raw_io.get_ebay_raw_dir", return_value=tmp_path), \
         patch("automana.core.services.app_integration.ebay.category_sweep_service.aioredis") as mock_aioredis, \
         patch.object(svc_mod, "_SWEEP_MAX_PAGES", 1):
        mock_settings.return_value = MagicMock(ebay_app_id=app_id, redis_host="localhost", redis_port=6379)
        mock_aioredis.from_url.return_value = mock_redis
        with patch.object(svc_mod, "_MARKETPLACES", ("EBAY-US",)):
            async with db_pool.acquire() as conn:
                result = await ebay_category_sweep(
                    ebay_sales_repository=EbaySalesRepository(conn),
                    ebay_scrape_repository=EbayScrapeSoldRepository(conn),
                    ebay_finding_repository=EbayFindingAPIRepository(environment="production"),
                )

    print(f"\n[live] fetched={result['fetched']}  matched={result['matched']}  inserted={result['inserted']}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sweep_file = tmp_path / today / "sweep" / "EBAY-US.json"
    assert sweep_file.exists(), "Sweep JSON file was not written to disk"

    assert result["fetched"] > 0, "eBay returned 0 items — check EBAY_APP_ID validity"
    assert result["matched"] >= 1, (
        f"0 items matched from {result['fetched']} fetched — "
        "check score threshold and that eBay-sourced cards exist in the DB"
    )

    # Cleanup
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pricing.ebay_scraped_sold WHERE source_product_id = $1",
            seeded_db["source_product_id"],
        )
```

- [ ] **Step 2: Run the CI-safe integration tests**

```bash
python -m pytest tests/integration/services/ebay/test_category_sweep.py \
    -k "not live" -v --timeout=120
```

Expected: `test_category_sweep_ingest` PASSED, `test_watchlist_pagination_ingest` PASSED.

- [ ] **Step 3: Confirm the existing promote test still passes**

```bash
python -m pytest tests/integration/services/ebay/ -k "not live" -v --timeout=120
```

Expected: all 3 tests PASSED (promote + sweep ingest + watchlist pagination).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/services/ebay/test_category_sweep.py
git commit -m "test(ebay): add integration tests for category sweep and watchlist pagination replay"
```

---

### Task 8: 7-day JSON file cleanup maintenance task

**Files:**
- Modify: `src/automana/worker/tasks/ebay.py`
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tasks/test_ebay_cleanup_task.py`:

```python
"""Unit test: cleanup task deletes files older than 7 days, leaves recent ones."""
from __future__ import annotations

import pytest
import time
from pathlib import Path
from unittest.mock import patch


def test_cleanup_deletes_old_files(tmp_path):
    from automana.worker.tasks.ebay import _cleanup_old_ebay_raw_files

    old_file = tmp_path / "2026-05-10" / "sweep" / "EBAY-US.json"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("{}")
    # Set mtime to 10 days ago
    old_time = time.time() - (10 * 86400)
    import os
    os.utime(old_file, (old_time, old_time))

    recent_file = tmp_path / "2026-05-24" / "sweep" / "EBAY-US.json"
    recent_file.parent.mkdir(parents=True)
    recent_file.write_text("{}")

    with patch("automana.worker.tasks.ebay.get_ebay_raw_dir", return_value=tmp_path):
        deleted = _cleanup_old_ebay_raw_files(max_age_days=7)

    assert not old_file.exists(), "Old file should have been deleted"
    assert recent_file.exists(), "Recent file should be kept"
    assert deleted == 1
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/unit/tasks/test_ebay_cleanup_task.py -v 2>&1 | head -20
```

Expected: ImportError — `_cleanup_old_ebay_raw_files` does not exist.

- [ ] **Step 3: Add `_cleanup_old_ebay_raw_files` and the Celery task to `tasks/ebay.py`**

Add the import at the top of `tasks/ebay.py`:

```python
from automana.core.services.app_integration.ebay.ebay_raw_io import get_ebay_raw_dir
```

Add below the existing tasks (after `ebay_category_sweep_task`):

```python
def _cleanup_old_ebay_raw_files(max_age_days: int = 7) -> int:
    """Delete JSON files under the ebay_raw directory older than max_age_days. Returns count deleted."""
    import time
    raw_dir = get_ebay_raw_dir()
    if not raw_dir.exists():
        return 0
    cutoff = time.time() - (max_age_days * 86_400)
    deleted = 0
    for f in raw_dir.rglob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            deleted += 1
    return deleted


@app.task(
    name="automana.worker.tasks.ebay.ebay_cleanup_raw_files_task",
    bind=True,
    acks_late=True,
    max_retries=0,
)
def ebay_cleanup_raw_files_task(self):
    """Weekly maintenance: delete eBay raw JSON files older than 7 days."""
    deleted = _cleanup_old_ebay_raw_files(max_age_days=7)
    logger.info("ebay_cleanup_raw_files_complete", extra={"deleted": deleted})
    return {"deleted": deleted}
```

- [ ] **Step 4: Add the weekly schedule entry to `celeryconfig.py`**

Add to the `beat_schedule` dict (alongside the other ebay entries added in Task 6):

```python
    "ebay-cleanup-raw-files-weekly": {
        "task": "automana.worker.tasks.ebay.ebay_cleanup_raw_files_task",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),  # Sunday 03:00 AEST
    },
```

- [ ] **Step 5: Run test to confirm it passes**

```bash
python -m pytest tests/unit/tasks/test_ebay_cleanup_task.py -v
```

Expected: 1 test PASSED.

- [ ] **Step 6: Verify Celery config imports cleanly**

```bash
python -c "from automana.worker import celeryconfig; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add src/automana/worker/tasks/ebay.py \
        src/automana/worker/celeryconfig.py \
        tests/unit/tasks/test_ebay_cleanup_task.py
git commit -m "feat(ebay): add weekly cleanup task for JSON files older than 7 days"
```

---

## Self-Review Checklist

All spec requirements are covered:

| Spec requirement | Task |
|---|---|
| `find_completed_items` pagination (max_pages, keywords=None) | Task 1 |
| `get_ebay_card_lookup()` DB method | Task 2 |
| JSON file write before DB insert (replay buffer) | Tasks 3, 4, 5 |
| Redis API quota guard shared across tasks | Tasks 3, 4, 5 |
| `EbayCategorySweepService` with 0.5 threshold | Task 4 |
| JSON staging in `scrape_global_market_service` (watchlist, max_pages=3) | Task 5 |
| New `ebay_category_sweep_task` Celery task | Task 6 |
| Schedule shifts (sweep 09:00, scrape 09:45, promote 10:30 AEST) | Task 6 |
| CI-safe integration tests (sweep ingest, watchlist pagination) | Task 7 |
| Live integration test (real eBay API, @pytest.mark.live) | Task 7 |
| 7-day JSON file cleanup maintenance task (weekly Celery beat) | Task 8 |

**Out of scope (confirmed not implemented):** `promote_sold_obs` changes, new `source_product` rows from unmatched items, FX normalisation, watchlist management.
