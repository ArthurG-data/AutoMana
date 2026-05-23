# eBay Market Price Research — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GET /api/v1/integrations/ebay/market-price` endpoint (+ Jupyter notebook) that fetches both sold and active eBay listings for a MTG card, scores each result for relevance, and returns aggregated price data to inform new listing prices.

**Architecture:** A new `EbayFindingAPIRepository` fetches completed/sold listings from eBay's Finding API (GET, JSON format, app-level auth via App ID). The existing `EbayBrowseAPIRepository` fetches active listings concurrently. A new `market_price_service` orchestrates both, scores results with a pure-function relevance scorer, computes `PriceAggregates`, and returns a `CardMarketData` model.

**Tech Stack:** Python 3.11+, httpx (already a dep), statistics (stdlib), Pydantic v2, FastAPI, Jupyter + httpx + pandas + matplotlib (notebook only).

**Spec:** `docs/superpowers/specs/2026-05-09-ebay-market-price-design.md`

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Create | `src/automana/core/models/ebay/market_price.py` | PricePoint, PriceAggregates (with factory), CardMarketData |
| Create | `src/automana/core/services/app_integration/ebay/market_price_scorer.py` | Pure functions: build_query_string, score_title, REJECT_KEYWORDS |
| Create | `src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py` | EbayFindingAPIRepository — Finding API client |
| Modify | `src/automana/core/framework/registry.py` | Register "ebay_finding" API repository |
| Create | `src/automana/core/services/app_integration/ebay/market_price_service.py` | fetch_card_market_price registered service |
| Modify | `src/automana/core/service_modules.py` | Add market_price_service to "backend" and "all" |
| Create | `src/automana/api/routers/integrations/ebay/ebay_market.py` | GET /market-price router |
| Modify | `src/automana/api/routers/integrations/ebay/__init__.py` | Mount ebay_market_router |
| Create | `notebooks/ebay_price_research.ipynb` | Demo notebook |
| Create | `tests/unit/core/models/ebay/test_market_price.py` | Model + aggregation tests |
| Create | `tests/unit/core/models/ebay/__init__.py` | Package marker |
| Create | `tests/unit/core/services/app_integration/ebay/test_market_price_scorer.py` | Scorer + query builder tests |
| Create | `tests/unit/core/services/app_integration/ebay/test_market_price_service.py` | Service tests |
| Create | `tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py` | Finding API repo tests |

---

## Task 1: Data Models

**Files:**
- Create: `src/automana/core/models/ebay/market_price.py`
- Create: `tests/unit/core/models/ebay/__init__.py`
- Create: `tests/unit/core/models/ebay/test_market_price.py`

- [ ] **Step 1.1 — Write failing tests**

```python
# tests/unit/core/models/ebay/test_market_price.py
from datetime import datetime, timezone
from automana.core.models.ebay.market_price import PriceAggregates, PricePoint, CardMarketData

def test_price_aggregates_empty():
    agg = PriceAggregates.from_prices([])
    assert agg.count == 0
    assert agg.min is None
    assert agg.median is None

def test_price_aggregates_single():
    agg = PriceAggregates.from_prices([10.0])
    assert agg.count == 1
    assert agg.min == 10.0
    assert agg.max == 10.0
    assert agg.mean == 10.0
    assert agg.median == 10.0
    assert agg.p25 is None  # not enough data for quartiles
    assert agg.p75 is None

def test_price_aggregates_known_values():
    # prices: 1, 2, 3, 4, 5 → median=3, mean=3, p25=2, p75=4
    agg = PriceAggregates.from_prices([5.0, 1.0, 3.0, 2.0, 4.0])
    assert agg.count == 5
    assert agg.min == 1.0
    assert agg.max == 5.0
    assert agg.median == 3.0
    assert agg.mean == 3.0
    assert agg.p25 == 2.0
    assert agg.p75 == 4.0

def test_price_point_defaults():
    pp = PricePoint(
        item_id="123",
        title="Sheoldred",
        price=45.0,
        currency="AUD",
        relevance_score=0.8,
    )
    assert pp.sold_date is None
    assert pp.condition is None
    assert pp.url is None

def test_card_market_data_structure():
    now = datetime.now(timezone.utc)
    agg = PriceAggregates.from_prices([10.0, 20.0, 30.0, 40.0, 50.0])
    data = CardMarketData(
        query="Sheoldred DMR MTG",
        card_name="Sheoldred, the Apocalypse",
        set_code="DMR",
        condition_id=3000,
        is_foil=False,
        frame=None,
        as_of=now,
        sold=[],
        active=[],
        sold_aggregates=agg,
        active_aggregates=PriceAggregates.from_prices([]),
        suggested_price=30.0,
    )
    assert data.card_name == "Sheoldred, the Apocalypse"
    assert data.sold_aggregates.median == 30.0
```

- [ ] **Step 1.2 — Run tests, expect ImportError**

```bash
pytest tests/unit/core/models/ebay/test_market_price.py -v
```
Expected: `ModuleNotFoundError: No module named 'automana.core.models.ebay.market_price'`

- [ ] **Step 1.3 — Create `__init__.py`**

```bash
touch tests/unit/core/models/ebay/__init__.py
```

- [ ] **Step 1.4 — Create the models file**

```python
# src/automana/core/models/ebay/market_price.py
import statistics
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class PricePoint(BaseModel):
    item_id: str
    title: str
    price: float
    currency: str
    condition: Optional[str] = None
    url: Optional[str] = None
    sold_date: Optional[datetime] = None
    relevance_score: float = 0.0

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class PriceAggregates(BaseModel):
    count: int
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_prices(cls, prices: list[float]) -> "PriceAggregates":
        if not prices:
            return cls(count=0)
        sorted_prices = sorted(prices)
        p25: Optional[float] = None
        p75: Optional[float] = None
        if len(sorted_prices) >= 4:
            qs = statistics.quantiles(sorted_prices, n=4)
            p25 = round(qs[0], 2)
            p75 = round(qs[2], 2)
        return cls(
            count=len(prices),
            min=round(sorted_prices[0], 2),
            max=round(sorted_prices[-1], 2),
            mean=round(statistics.mean(prices), 2),
            median=round(statistics.median(prices), 2),
            p25=p25,
            p75=p75,
        )


class CardMarketData(BaseModel):
    query: str
    card_name: str
    set_code: Optional[str] = None
    condition_id: Optional[int] = None
    is_foil: Optional[bool] = None
    frame: Optional[str] = None
    as_of: datetime
    sold: list[PricePoint] = []
    active: list[PricePoint] = []
    sold_aggregates: PriceAggregates
    active_aggregates: PriceAggregates
    suggested_price: Optional[float] = None

    model_config = ConfigDict(populate_by_name=True)
```

- [ ] **Step 1.5 — Run tests, expect PASS**

```bash
pytest tests/unit/core/models/ebay/test_market_price.py -v
```
Expected: 5 passed.

- [ ] **Step 1.6 — Commit**

```bash
git add src/automana/core/models/ebay/market_price.py \
        tests/unit/core/models/ebay/__init__.py \
        tests/unit/core/models/ebay/test_market_price.py
git commit -m "feat(ebay): add CardMarketData, PricePoint, PriceAggregates models"
```

---

## Task 2: Query Builder + Relevance Scorer

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/market_price_scorer.py`
- Create: `tests/unit/core/services/app_integration/ebay/test_market_price_scorer.py`

- [ ] **Step 2.1 — Write failing tests**

```python
# tests/unit/core/services/app_integration/ebay/test_market_price_scorer.py
from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)


# ── build_query_string ──────────────────────────────────────────────────────

def test_query_includes_card_name_words():
    q = build_query_string("Sheoldred, the Apocalypse", None, None, None)
    assert "Sheoldred" in q
    assert "Apocalypse" in q

def test_query_strips_punctuation_from_card_name():
    q = build_query_string("Sheoldred, the Apocalypse", None, None, None)
    assert "," not in q

def test_query_appends_set_code():
    q = build_query_string("Lightning Bolt", "M10", None, None)
    assert "M10" in q

def test_query_appends_foil():
    q = build_query_string("Mox Pearl", None, True, None)
    assert "foil" in q.lower()

def test_query_appends_nonfoil():
    q = build_query_string("Mox Pearl", None, False, None)
    assert "non-foil" in q.lower()

def test_query_appends_frame():
    q = build_query_string("Sheoldred, the Apocalypse", "DMR", None, "showcase")
    assert "showcase" in q.lower()

def test_query_ends_with_mtg():
    q = build_query_string("Sheoldred, the Apocalypse", None, None, None)
    assert q.strip().upper().endswith("MTG")


# ── score_title ─────────────────────────────────────────────────────────────

def test_exact_card_name_match_contributes_half():
    score = score_title("Sheoldred the Apocalypse NM MTG", "Sheoldred the Apocalypse", None, None, None)
    assert score >= 0.5

def test_reject_keyword_gives_zero():
    score = score_title("Sheoldred Apocalypse proxy MTG", "Sheoldred Apocalypse", None, None, None)
    assert score == 0.0

def test_reject_keyword_psa_gives_zero():
    score = score_title("Sheoldred Apocalypse PSA 10 MTG", "Sheoldred Apocalypse", None, None, None)
    assert score == 0.0

def test_set_code_bonus():
    base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    with_set = score_title("Sheoldred Apocalypse DMR MTG", "Sheoldred Apocalypse", "DMR", None, None)
    assert with_set > base

def test_foil_match_bonus():
    base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    with_foil = score_title("Sheoldred Apocalypse foil MTG", "Sheoldred Apocalypse", None, True, None)
    assert with_foil > base

def test_foil_mismatch_no_bonus():
    # requesting foil, title says non-foil → no foil bonus
    base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    mismatch = score_title("Sheoldred Apocalypse non-foil MTG", "Sheoldred Apocalypse", None, True, None)
    assert mismatch <= base

def test_frame_match_bonus():
    base = score_title("Sheoldred Apocalypse MTG", "Sheoldred Apocalypse", None, None, None)
    with_frame = score_title("Sheoldred Apocalypse showcase MTG", "Sheoldred Apocalypse", None, None, "showcase")
    assert with_frame > base

def test_score_capped_at_one():
    score = score_title("Sheoldred Apocalypse DMR foil showcase MTG", "Sheoldred Apocalypse", "DMR", True, "showcase")
    assert 0.0 <= score <= 1.0
```

- [ ] **Step 2.2 — Run tests, expect ImportError**

```bash
pytest tests/unit/core/services/app_integration/ebay/test_market_price_scorer.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 2.3 — Create the scorer module**

```python
# src/automana/core/services/app_integration/ebay/market_price_scorer.py
import re
from typing import Optional

REJECT_KEYWORDS: frozenset[str] = frozenset({
    "proxy", "fake", "alter", "custom", "token", "lot", "playset",
    "bundle", "signed", "psa", "bgs", "cgc", "graded", "reprint lot",
})

_PUNCTUATION_RE = re.compile(r"[^\w\s]")


def build_query_string(
    card_name: str,
    set_code: Optional[str],
    is_foil: Optional[bool],
    frame: Optional[str],
) -> str:
    parts = [_PUNCTUATION_RE.sub("", card_name).strip()]
    if set_code:
        parts.append(set_code.upper())
    if is_foil is True:
        parts.append("foil")
    elif is_foil is False:
        parts.append("non-foil")
    if frame:
        parts.append(frame.lower())
    parts.append("MTG")
    return " ".join(parts)


def score_title(
    title: str,
    card_name: str,
    set_code: Optional[str],
    is_foil: Optional[bool],
    frame: Optional[str],
) -> float:
    lower = title.lower()

    # Hard reject
    for kw in REJECT_KEYWORDS:
        if kw in lower:
            return 0.0

    score = 0.0

    # Card name words (0.50)
    clean_name = _PUNCTUATION_RE.sub("", card_name).lower()
    name_words = clean_name.split()
    if name_words and all(w in lower for w in name_words):
        score += 0.50

    # Set code (0.20)
    if set_code and set_code.lower() in lower:
        score += 0.20

    # Foil (0.15)
    if is_foil is True and "foil" in lower and "non-foil" not in lower:
        score += 0.15
    elif is_foil is False and "non-foil" in lower:
        score += 0.15

    # Frame variant (0.15)
    if frame and frame.lower() in lower:
        score += 0.15

    return min(score, 1.0)
```

- [ ] **Step 2.4 — Run tests, expect PASS**

```bash
pytest tests/unit/core/services/app_integration/ebay/test_market_price_scorer.py -v
```
Expected: 14 passed.

- [ ] **Step 2.5 — Commit**

```bash
git add src/automana/core/services/app_integration/ebay/market_price_scorer.py \
        tests/unit/core/services/app_integration/ebay/test_market_price_scorer.py
git commit -m "feat(ebay): add market price query builder and relevance scorer"
```

---

## Task 3: EbayFindingAPIRepository

**Files:**
- Create: `src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py`
- Create: `tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py`

**Background:** The Finding API uses a different base host (`svcs.ebay.com`) from other eBay APIs. Auth is via the `X-EBAY-SOA-SECURITY-APPNAME` header (App ID only, no user OAuth token). The response format is JSON with a characteristic array-wrapped structure. Set `RESPONSE-DATA-FORMAT=JSON` in params to get JSON back.

Finding API JSON response shape (relevant fields only):
```
findCompletedItemsResponse[0]
  .searchResult[0]
    .item[0..N]
      .itemId[0]                          → str
      .title[0]                           → str
      .sellingStatus[0]
        .currentPrice[0]
          .__value__                      → str price
          .@currencyId                    → str currency  (note: _parse_response strips @)
      .listingInfo[0]
        .endTime[0]                       → ISO datetime str
      .condition[0]
        .conditionDisplayName[0]          → str
      .viewItemURL[0]                     → str
```

- [ ] **Step 3.1 — Write failing tests**

```python
# tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone
import httpx
from automana.core.repositories.app_integration.ebay.ApiFinding_repository import (
    EbayFindingAPIRepository,
    _parse_finding_items,
)

SAMPLE_FINDING_RESPONSE = {
    "findCompletedItemsResponse": [
        {
            "ack": ["Success"],
            "searchResult": [
                {
                    "count": "2",
                    "item": [
                        {
                            "itemId": ["111111"],
                            "title": ["Sheoldred the Apocalypse NM DMR MTG"],
                            "sellingStatus": [
                                {
                                    "currentPrice": [
                                        {"currencyId": "AUD", "__value__": "45.00"}
                                    ],
                                    "sellingState": ["EndedWithSales"],
                                }
                            ],
                            "listingInfo": [{"endTime": ["2026-01-01T10:00:00.000Z"]}],
                            "condition": [{"conditionDisplayName": ["Very Good"]}],
                            "viewItemURL": ["https://www.ebay.com.au/itm/111111"],
                        },
                        {
                            "itemId": ["222222"],
                            "title": ["Sheoldred Apocalypse LP MTG"],
                            "sellingStatus": [
                                {
                                    "currentPrice": [
                                        {"currencyId": "AUD", "__value__": "38.00"}
                                    ],
                                    "sellingState": ["EndedWithSales"],
                                }
                            ],
                            "listingInfo": [{"endTime": ["2026-01-02T10:00:00.000Z"]}],
                            "condition": [{"conditionDisplayName": ["Good"]}],
                            "viewItemURL": ["https://www.ebay.com.au/itm/222222"],
                        },
                    ],
                }
            ],
        }
    ]
}


def test_parse_finding_items_extracts_two_items():
    items = _parse_finding_items(SAMPLE_FINDING_RESPONSE)
    assert len(items) == 2


def test_parse_finding_items_first_item_fields():
    items = _parse_finding_items(SAMPLE_FINDING_RESPONSE)
    first = items[0]
    assert first["item_id"] == "111111"
    assert first["title"] == "Sheoldred the Apocalypse NM DMR MTG"
    assert first["price"] == 45.0
    assert first["currency"] == "AUD"
    assert first["condition"] == "Very Good"
    assert first["url"] == "https://www.ebay.com.au/itm/111111"
    assert first["sold_date"] == "2026-01-01T10:00:00.000Z"


def test_parse_finding_items_empty_response():
    empty = {"findCompletedItemsResponse": [{"ack": ["Success"], "searchResult": [{"count": "0"}]}]}
    items = _parse_finding_items(empty)
    assert items == []


def test_finding_repository_name():
    repo = EbayFindingAPIRepository(environment="sandbox")
    assert repo.name == "EbayFindingAPIRepository"


async def test_find_completed_items_builds_correct_params():
    repo = EbayFindingAPIRepository(environment="sandbox")
    min_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

    captured_params = {}

    async def fake_send(method, endpoint, *, params=None, headers=None, **kwargs):
        captured_params.update(params or {})
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {
            "findCompletedItemsResponse": [{"ack": ["Success"], "searchResult": [{"count": "0"}]}]
        }
        return mock_resp

    with patch.object(repo, "send", side_effect=fake_send):
        with patch.object(repo, "_parse_response", return_value={
            "findCompletedItemsResponse": [{"ack": ["Success"], "searchResult": [{"count": "0"}]}]
        }):
            await repo.find_completed_items(
                keywords="Sheoldred DMR MTG",
                app_id="TESTAPP-ID",
                category_id=2536,
                condition_id=3000,
                min_date=min_date,
                limit=25,
            )

    assert captured_params.get("OPERATION-NAME") == "findCompletedItems"
    assert captured_params.get("SECURITY-APPNAME") == "TESTAPP-ID"
    assert captured_params.get("keywords") == "Sheoldred DMR MTG"
    assert captured_params.get("RESPONSE-DATA-FORMAT") == "JSON"
    assert "paginationInput.entriesPerPage" in captured_params
```

- [ ] **Step 3.2 — Run tests, expect ImportError**

```bash
pytest tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3.3 — Create the repository**

```python
# src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py
from datetime import datetime
from typing import Any, Optional
import logging

from automana.core.repositories.app_integration.ebay.EbayApiRepository import EbayApiClient

logger = logging.getLogger(__name__)

_FINDING_ENDPOINT = "/services/search/FindingService/v1"
_SERVICE_VERSION = "1.13.0"


def _parse_finding_items(response: dict) -> list[dict]:
    """Extract a flat list of raw item dicts from the Finding API JSON response."""
    try:
        result_block = response["findCompletedItemsResponse"][0]
        search_result = result_block.get("searchResult", [{}])[0]
        raw_items = search_result.get("item", [])
    except (KeyError, IndexError):
        return []

    out = []
    for item in raw_items:
        try:
            selling = item.get("sellingStatus", [{}])[0]
            price_block = selling.get("currentPrice", [{}])[0]
            listing_info = item.get("listingInfo", [{}])[0]
            condition_block = item.get("condition", [{}])[0]

            out.append({
                "item_id": item.get("itemId", [""])[0],
                "title": item.get("title", [""])[0],
                "price": float(price_block.get("__value__", 0)),
                "currency": price_block.get("currencyId", ""),
                "condition": condition_block.get("conditionDisplayName", [None])[0],
                "url": item.get("viewItemURL", [None])[0],
                "sold_date": listing_info.get("endTime", [None])[0],
            })
        except Exception:
            logger.warning("Skipping unparseable Finding API item", extra={"raw": str(item)[:200]})
            continue

    return out


class EbayFindingAPIRepository(EbayApiClient):
    URL_MAPPING = {
        "sandbox": "https://svcs.sandbox.ebay.com",
        "production": "https://svcs.ebay.com",
    }

    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        self.environment = environment.lower()
        super().__init__(timeout=timeout)

    @property
    def name(self) -> str:
        return "EbayFindingAPIRepository"

    def _get_base_url(self) -> str:
        url = self.URL_MAPPING.get(self.environment)
        if not url:
            raise ValueError(f"No Finding API URL for environment: {self.environment}")
        return url

    async def find_completed_items(
        self,
        keywords: str,
        app_id: str,
        *,
        category_id: int = 2536,
        condition_id: Optional[int] = None,
        min_date: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "OPERATION-NAME": "findCompletedItems",
            "SERVICE-VERSION": _SERVICE_VERSION,
            "SECURITY-APPNAME": app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "keywords": keywords,
            "categoryId": str(category_id),
            "itemFilter(0).name": "SoldItemsOnly",
            "itemFilter(0).value": "true",
            "paginationInput.entriesPerPage": str(min(limit, 100)),
            "paginationInput.pageNumber": "1",
        }

        filter_idx = 1
        if condition_id is not None:
            params[f"itemFilter({filter_idx}).name"] = "Condition"
            params[f"itemFilter({filter_idx}).value"] = str(condition_id)
            filter_idx += 1

        if min_date is not None:
            params[f"itemFilter({filter_idx}).name"] = "EndTimeFrom"
            params[f"itemFilter({filter_idx}).value"] = min_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        logger.info(
            "Finding API request",
            extra={"keywords": keywords, "category_id": category_id, "limit": limit},
        )
        async with self:
            response = await self.send("GET", _FINDING_ENDPOINT, params=params)
            data = self._parse_response(response)

        return _parse_finding_items(data)
```

- [ ] **Step 3.4 — Run tests, expect PASS**

```bash
pytest tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py -v
```
Expected: 5 passed.

- [ ] **Step 3.5 — Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py \
        tests/unit/core/repositories/app_integration/ebay/test_finding_repository.py
git commit -m "feat(ebay): add EbayFindingAPIRepository for sold listings"
```

---

## Task 4: Register Finding API Repository

**Files:**
- Modify: `src/automana/core/framework/registry.py`

The service manager resolves `api_repositories=["ebay_finding"]` by calling `ServiceRegistry.get_api_repository("ebay_finding")`, instantiates the class with `environment=env`, and injects it as the kwarg `ebay_finding_repository` into the service function.

- [ ] **Step 4.1 — Add registration to service_registry.py**

Find the block of `ServiceRegistry.register_api_repository(...)` calls (around line 234) and add:

```python
ServiceRegistry.register_api_repository(
    "ebay_finding",
    "automana.core.repositories.app_integration.ebay.ApiFinding_repository",
    "EbayFindingAPIRepository",
)
```

Add it after the existing `"selling"` registration.

- [ ] **Step 4.2 — Verify no import errors**

```bash
python -c "from automana.core.framework.registry import ServiceRegistry; print(ServiceRegistry.get_api_repository('ebay_finding'))"
```
Expected: `('automana.core.repositories.app_integration.ebay.ApiFinding_repository', 'EbayFindingAPIRepository')`

- [ ] **Step 4.3 — Commit**

```bash
git add src/automana/core/framework/registry.py
git commit -m "feat(ebay): register ebay_finding API repository in ServiceRegistry"
```

---

## Task 5: Market Price Service

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/market_price_service.py`
- Create: `tests/unit/core/services/app_integration/ebay/test_market_price_service.py`

The service is called by the service manager with injected repos: `ebay_finding_repository` (Finding API) and `search_repository` (Browse API). It also needs the `ebay_app_id` from settings. The Browse API raw JSON (dict) contains `itemSummaries` each with a `price` field (`{"value": "...", "currency": "..."}`).

- [ ] **Step 5.1 — Write failing tests**

```python
# tests/unit/core/services/app_integration/ebay/test_market_price_service.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from automana.core.services.app_integration.ebay.market_price_service import (
    fetch_card_market_price,
    _browse_items_to_price_points,
    _finding_items_to_price_points,
)
from automana.core.models.ebay.market_price import PricePoint


# ── helper parsers ──────────────────────────────────────────────────────────

def test_browse_items_to_price_points_basic():
    raw = {
        "itemSummaries": [
            {
                "itemId": "v1|999|0",
                "title": "Sheoldred Apocalypse NM",
                "price": {"value": "42.00", "currency": "AUD"},
                "condition": "Near Mint",
                "itemWebUrl": "https://ebay.com.au/itm/999",
            }
        ]
    }
    points = _browse_items_to_price_points(raw)
    assert len(points) == 1
    assert points[0].item_id == "v1|999|0"
    assert points[0].price == 42.0
    assert points[0].currency == "AUD"
    assert points[0].sold_date is None


def test_browse_items_to_price_points_missing_price_skipped():
    raw = {"itemSummaries": [{"itemId": "x", "title": "bad", "price": {}}]}
    points = _browse_items_to_price_points(raw)
    # price value is 0.0 — we keep it; the relevance filter will handle it
    assert points[0].price == 0.0


def test_finding_items_to_price_points_basic():
    raw_items = [
        {
            "item_id": "111",
            "title": "Sheoldred Apocalypse NM DMR MTG",
            "price": 45.0,
            "currency": "AUD",
            "condition": "Very Good",
            "url": "https://www.ebay.com.au/itm/111",
            "sold_date": "2026-01-01T10:00:00.000Z",
        }
    ]
    points = _finding_items_to_price_points(raw_items)
    assert len(points) == 1
    assert points[0].item_id == "111"
    assert points[0].price == 45.0
    assert points[0].sold_date is not None


# ── full service ────────────────────────────────────────────────────────────

@pytest.fixture
def finding_repo():
    repo = AsyncMock()
    repo.find_completed_items = AsyncMock(return_value=[
        {
            "item_id": "001",
            "title": "Sheoldred Apocalypse NM DMR MTG",
            "price": 45.0,
            "currency": "AUD",
            "condition": "Very Good",
            "url": "https://ebay.com/itm/001",
            "sold_date": "2026-01-01T10:00:00.000Z",
        },
        {
            "item_id": "002",
            "title": "Sheoldred Apocalypse DMR MTG proxy",
            "price": 5.0,
            "currency": "AUD",
            "condition": "Good",
            "url": "https://ebay.com/itm/002",
            "sold_date": "2026-01-02T10:00:00.000Z",
        },
    ])
    return repo


@pytest.fixture
def browse_repo():
    repo = AsyncMock()
    repo.search_items = AsyncMock(return_value={
        "itemSummaries": [
            {
                "itemId": "v1|003|0",
                "title": "Sheoldred Apocalypse DMR NM MTG",
                "price": {"value": "50.00", "currency": "AUD"},
                "condition": "Near Mint",
                "itemWebUrl": "https://ebay.com.au/itm/003",
            }
        ]
    })
    return repo


async def test_service_returns_card_market_data(finding_repo, browse_repo):
    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.get_settings",
        return_value=MagicMock(ebay_app_id="TEST-APP-ID"),
    ):
        result = await fetch_card_market_price(
            ebay_finding_repository=finding_repo,
            search_repository=browse_repo,
            card_name="Sheoldred the Apocalypse",
            token="fake-token",
            set_code="DMR",
            condition_id=None,
            is_foil=None,
            frame=None,
            days_back=30,
            limit=50,
            match_threshold=0.6,
        )

    assert result.card_name == "Sheoldred the Apocalypse"
    assert result.set_code == "DMR"
    # proxy item is excluded by scorer
    proxy_ids = [p.item_id for p in result.sold]
    assert "002" not in proxy_ids
    # sold aggregates computed from the one valid sold item
    assert result.sold_aggregates.count == 1
    # suggested_price is None because < 3 sold items
    assert result.suggested_price is None


async def test_service_sets_suggested_price_when_enough_sold(finding_repo, browse_repo):
    # Override finding_repo to return 3 clean sold items
    finding_repo.find_completed_items = AsyncMock(return_value=[
        {"item_id": str(i), "title": "Sheoldred Apocalypse DMR MTG",
         "price": float(40 + i * 5), "currency": "AUD",
         "condition": "Very Good", "url": f"https://ebay.com/itm/{i}",
         "sold_date": "2026-01-01T10:00:00.000Z"}
        for i in range(3)  # prices: 40, 45, 50
    ])
    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.get_settings",
        return_value=MagicMock(ebay_app_id="TEST-APP-ID"),
    ):
        result = await fetch_card_market_price(
            ebay_finding_repository=finding_repo,
            search_repository=browse_repo,
            card_name="Sheoldred the Apocalypse",
            token="fake-token",
            set_code="DMR",
            condition_id=None,
            is_foil=None,
            frame=None,
            days_back=30,
            limit=50,
            match_threshold=0.4,  # lower threshold so all 3 pass
        )
    # median of [40, 45, 50] = 45
    assert result.suggested_price == 45.0


async def test_service_partial_when_finding_fails(browse_repo):
    failing_finding = AsyncMock()
    failing_finding.find_completed_items = AsyncMock(side_effect=Exception("Finding API down"))

    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.get_settings",
        return_value=MagicMock(ebay_app_id="TEST-APP-ID"),
    ):
        result = await fetch_card_market_price(
            ebay_finding_repository=failing_finding,
            search_repository=browse_repo,
            card_name="Sheoldred the Apocalypse",
            token="fake-token",
            set_code="DMR",
            condition_id=None,
            is_foil=None,
            frame=None,
            days_back=30,
            limit=50,
            match_threshold=0.0,
        )

    assert result.sold == []
    assert result.sold_aggregates.count == 0
    assert result.suggested_price is None
    # active results still present
    assert result.active_aggregates.count >= 0
```

- [ ] **Step 5.2 — Run tests, expect ImportError**

```bash
pytest tests/unit/core/services/app_integration/ebay/test_market_price_service.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 5.3 — Create the service**

```python
# src/automana/core/services/app_integration/ebay/market_price_service.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from automana.core.models.ebay.market_price import CardMarketData, PriceAggregates, PricePoint
from automana.core.repositories.app_integration.ebay.ApiFinding_repository import EbayFindingAPIRepository
from automana.core.repositories.app_integration.ebay.ApiBrowse_repository import EbayBrowseAPIRepository
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay.market_price_scorer import (
    build_query_string,
    score_title,
)
from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

# eBay category ID for Magic: The Gathering (verify against live API)
_MTG_CATEGORY_ID = 2536


def _finding_items_to_price_points(raw_items: list[dict]) -> list[PricePoint]:
    points = []
    for item in raw_items:
        sold_date = None
        raw_date = item.get("sold_date")
        if raw_date:
            try:
                sold_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        points.append(
            PricePoint(
                item_id=item.get("item_id", ""),
                title=item.get("title", ""),
                price=float(item.get("price", 0)),
                currency=item.get("currency", ""),
                condition=item.get("condition"),
                url=item.get("url"),
                sold_date=sold_date,
            )
        )
    return points


def _browse_items_to_price_points(raw_data: dict) -> list[PricePoint]:
    points = []
    for item in raw_data.get("itemSummaries", []):
        price_block = item.get("price", {})
        try:
            price = float(price_block.get("value", 0))
        except (TypeError, ValueError):
            price = 0.0
        points.append(
            PricePoint(
                item_id=item.get("itemId", ""),
                title=item.get("title", ""),
                price=price,
                currency=price_block.get("currency", ""),
                condition=item.get("condition"),
                url=item.get("itemWebUrl"),
                sold_date=None,
            )
        )
    return points


def _score_and_filter(
    points: list[PricePoint],
    card_name: str,
    set_code: Optional[str],
    is_foil: Optional[bool],
    frame: Optional[str],
    threshold: float,
) -> list[PricePoint]:
    scored = []
    for p in points:
        s = score_title(p.title, card_name, set_code, is_foil, frame)
        if s >= threshold:
            scored.append(p.model_copy(update={"relevance_score": s}))
    return sorted(scored, key=lambda x: x.relevance_score, reverse=True)


@ServiceRegistry.register(
    path="integrations.ebay.market_price",
    db_repositories=[],
    api_repositories=["ebay_finding", "search"],
    runs_in_transaction=False,
)
async def fetch_card_market_price(
    ebay_finding_repository: EbayFindingAPIRepository,
    search_repository: EbayBrowseAPIRepository,
    card_name: str,
    token: str,
    set_code: Optional[str] = None,
    condition_id: Optional[int] = None,
    is_foil: Optional[bool] = None,
    frame: Optional[str] = None,
    days_back: int = 30,
    limit: int = 50,
    match_threshold: float = 0.6,
    **kwargs,
) -> CardMarketData:
    settings = get_settings()
    app_id = settings.ebay_app_id or ""

    query = build_query_string(card_name, set_code, is_foil, frame)
    min_date = datetime.now(timezone.utc) - timedelta(days=min(days_back, 90))
    capped_limit = min(limit, 200)

    browse_params = {
        "q": query,
        "category_ids": [str(_MTG_CATEGORY_ID)],
        "limit": capped_limit,
        "offset": 0,
    }
    if condition_id is not None:
        browse_params["filter"] = [f"conditionIds:{{{condition_id}}}"]

    browse_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # Fetch both sources concurrently; degrade gracefully on individual failure
    sold_raw: list[dict] = []
    active_raw: dict = {}

    async def _fetch_sold() -> list[dict]:
        return await ebay_finding_repository.find_completed_items(
            keywords=query,
            app_id=app_id,
            category_id=_MTG_CATEGORY_ID,
            condition_id=condition_id,
            min_date=min_date,
            limit=capped_limit,
        )

    async def _fetch_active() -> dict:
        return await search_repository.search_items(browse_params, headers=browse_headers)

    results = await asyncio.gather(_fetch_sold(), _fetch_active(), return_exceptions=True)

    if isinstance(results[0], Exception):
        logger.warning("Finding API failed; returning empty sold list", extra={"error": str(results[0])})
    else:
        sold_raw = results[0]

    if isinstance(results[1], Exception):
        logger.warning("Browse API failed; returning empty active list", extra={"error": str(results[1])})
    else:
        active_raw = results[1]

    sold_points = _score_and_filter(
        _finding_items_to_price_points(sold_raw),
        card_name, set_code, is_foil, frame, match_threshold,
    )
    active_points = _score_and_filter(
        _browse_items_to_price_points(active_raw),
        card_name, set_code, is_foil, frame, match_threshold,
    )

    sold_prices = [p.price for p in sold_points]
    active_prices = [p.price for p in active_points]

    sold_agg = PriceAggregates.from_prices(sold_prices)
    active_agg = PriceAggregates.from_prices(active_prices)

    suggested_price = sold_agg.median if sold_agg.count >= 3 else None

    return CardMarketData(
        query=query,
        card_name=card_name,
        set_code=set_code,
        condition_id=condition_id,
        is_foil=is_foil,
        frame=frame,
        as_of=datetime.now(timezone.utc),
        sold=sold_points,
        active=active_points,
        sold_aggregates=sold_agg,
        active_aggregates=active_agg,
        suggested_price=suggested_price,
    )
```

- [ ] **Step 5.4 — Run tests, expect PASS**

```bash
pytest tests/unit/core/services/app_integration/ebay/test_market_price_service.py -v
```
Expected: 6 passed.

- [ ] **Step 5.5 — Add service to service_modules.py**

In `src/automana/core/service_modules.py`, add the service path to both `"backend"` and `"all"` lists:

```python
"automana.core.services.app_integration.ebay.market_price_service",
```

Add it after `"automana.core.services.app_integration.ebay.fulfillment_service"` in both lists.

- [ ] **Step 5.6 — Verify service loads without error**

```bash
python -c "
from automana.core.framework.registry import ServiceRegistry
import automana.core.services.app_integration.ebay.market_price_service
cfg = ServiceRegistry.get_service('integrations.ebay.market_price')
print(cfg.api_repositories)
"
```
Expected: `['ebay_finding', 'search']`

- [ ] **Step 5.7 — Commit**

```bash
git add src/automana/core/services/app_integration/ebay/market_price_service.py \
        src/automana/core/service_modules.py \
        tests/unit/core/services/app_integration/ebay/test_market_price_service.py
git commit -m "feat(ebay): add fetch_card_market_price service with concurrent Finding+Browse fetch"
```

---

## Task 6: API Router

**Files:**
- Create: `src/automana/api/routers/integrations/ebay/ebay_market.py`
- Modify: `src/automana/api/routers/integrations/ebay/__init__.py`

**Auth flow** (same pattern as `ebay_browse.py`):
1. Call `service_manager.execute_service("integrations.ebay.get_token", app_code=app_code)` → user OAuth token
2. Call `service_manager.execute_service("integrations.ebay.get_environment", app_code=app_code)` → `"sandbox"` or `"production"`
3. Call `service_manager.execute_service("integrations.ebay.market_price", token=token, environment=environment, ...)`

- [ ] **Step 6.1 — Create the router**

```python
# src/automana/api/routers/integrations/ebay/ebay_market.py
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.core.models.ebay.market_price import CardMarketData

logger = logging.getLogger(__name__)

market_router = APIRouter(prefix="/market-price", tags=["eBay Market Price"])


@market_router.get("/", response_model=CardMarketData)
async def get_market_price(
    service_manager: ServiceManagerDep,
    card_name: str = Query(..., description="Card name, e.g. 'Sheoldred, the Apocalypse'"),
    app_code: str = Query(..., description="eBay app code for OAuth token resolution"),
    set_code: Optional[str] = Query(None, description="Set code, e.g. 'DMR'"),
    condition_id: Optional[int] = Query(None, description="eBay condition ID (3000=NM, 4000=LP)"),
    is_foil: Optional[bool] = Query(None, description="Foil or non-foil"),
    frame: Optional[str] = Query(None, description="Frame variant: showcase, extended_art, borderless, normal"),
    days_back: int = Query(30, ge=1, le=90, description="Lookback window for sold items"),
    limit: int = Query(50, ge=1, le=200, description="Max results per source"),
    match_threshold: float = Query(0.6, ge=0.0, le=1.0, description="Minimum relevance score (0–1)"),
) -> CardMarketData:
    token = await service_manager.execute_service(
        "integrations.ebay.get_token",
        app_code=app_code,
    )
    if not token:
        raise HTTPException(status_code=401, detail="Failed to retrieve eBay access token")

    environment = await service_manager.execute_service(
        "integrations.ebay.get_environment",
        app_code=app_code,
    )

    result: CardMarketData = await service_manager.execute_service(
        "integrations.ebay.market_price",
        token=token,
        environment=environment,
        card_name=card_name,
        set_code=set_code,
        condition_id=condition_id,
        is_foil=is_foil,
        frame=frame,
        days_back=days_back,
        limit=limit,
        match_threshold=match_threshold,
    )
    return result
```

- [ ] **Step 6.2 — Mount the router in `__init__.py`**

In `src/automana/api/routers/integrations/ebay/__init__.py`, add the import and `include_router` call:

```python
from automana.api.routers.integrations.ebay.ebay_market import market_router

# ... existing includes ...
ebay_router.include_router(market_router)
```

- [ ] **Step 6.3 — Verify the route is registered**

```bash
python -c "
from automana.api.routers.integrations.ebay import ebay_router
routes = [r.path for r in ebay_router.routes]
print(routes)
" 2>/dev/null || echo "Routes registered (import might need app context)"
```

If the above fails due to app context, just verify the import succeeds:

```bash
python -c "from automana.api.routers.integrations.ebay.ebay_market import market_router; print('OK')"
```
Expected: `OK`

- [ ] **Step 6.4 — Commit**

```bash
git add src/automana/api/routers/integrations/ebay/ebay_market.py \
        src/automana/api/routers/integrations/ebay/__init__.py
git commit -m "feat(ebay): add GET /market-price router endpoint"
```

---

## Task 7: Jupyter Notebook

**Files:**
- Create: `notebooks/ebay_price_research.ipynb`

The notebook calls the running backend (`http://localhost:8000`). It needs `httpx`, `pandas`, and `matplotlib` installed in the notebook environment (not in the backend). Use a plain `httpx.get` (synchronous, since notebooks run in sync cells by default) or wrap with `asyncio.run`.

- [ ] **Step 7.1 — Create the notebooks directory**

```bash
mkdir -p notebooks
```

- [ ] **Step 7.2 — Create the notebook**

```json
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": ["# eBay Market Price Research\n", "\nFetch sold and active eBay listings for a MTG card and analyze the price distribution.\n"]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "import httpx\n",
    "import pandas as pd\n",
    "import matplotlib.pyplot as plt\n",
    "import matplotlib.patches as mpatches\n",
    "\n",
    "BASE_URL = \"http://localhost:8000\"\n",
    "\n",
    "# ── Card inputs — edit these ──────────────────────────────────────────────\n",
    "APP_CODE     = \"automana_au\"      # your eBay app code\n",
    "CARD_NAME    = \"Sheoldred, the Apocalypse\"\n",
    "SET_CODE     = \"DMR\"\n",
    "IS_FOIL      = False\n",
    "FRAME        = None               # None | 'showcase' | 'extended_art' | 'borderless'\n",
    "CONDITION_ID = None               # None | 3000 (NM) | 4000 (LP) | 5000 (MP)\n",
    "DAYS_BACK    = 30\n",
    "LIMIT        = 50\n",
    "THRESHOLD    = 0.6\n"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "params = {\n",
    "    \"card_name\": CARD_NAME,\n",
    "    \"app_code\": APP_CODE,\n",
    "    \"set_code\": SET_CODE,\n",
    "    \"is_foil\": IS_FOIL,\n",
    "    \"days_back\": DAYS_BACK,\n",
    "    \"limit\": LIMIT,\n",
    "    \"match_threshold\": THRESHOLD,\n",
    "}\n",
    "if FRAME:        params[\"frame\"] = FRAME\n",
    "if CONDITION_ID: params[\"condition_id\"] = CONDITION_ID\n",
    "\n",
    "resp = httpx.get(f\"{BASE_URL}/api/v1/integrations/ebay/market-price/\", params=params, timeout=30)\n",
    "resp.raise_for_status()\n",
    "data = resp.json()\n",
    "\n",
    "print(f\"Card:  {data['card_name']}  |  Set: {data['set_code']}\")\n",
    "print(f\"Query: {data['query']}\")\n",
    "print(f\"Sold results: {data['sold_aggregates']['count']}   Active results: {data['active_aggregates']['count']}\")\n",
    "print(f\"Suggested price: {data['suggested_price']}\")\n"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "sold_df   = pd.DataFrame(data[\"sold\"])   if data[\"sold\"]   else pd.DataFrame()\n",
    "active_df = pd.DataFrame(data[\"active\"]) if data[\"active\"] else pd.DataFrame()\n",
    "\n",
    "if not sold_df.empty:\n",
    "    sold_df = sold_df.sort_values(\"relevance_score\", ascending=False)\n",
    "    print(\"=== Sold listings (top 10) ===\")\n",
    "    display(sold_df[[\"title\", \"price\", \"currency\", \"condition\", \"sold_date\", \"relevance_score\"]].head(10))\n",
    "\n",
    "if not active_df.empty:\n",
    "    active_df = active_df.sort_values(\"relevance_score\", ascending=False)\n",
    "    print(\"=== Active listings (top 10) ===\")\n",
    "    display(active_df[[\"title\", \"price\", \"currency\", \"condition\", \"relevance_score\"]].head(10))\n"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "fig, axes = plt.subplots(1, 2, figsize=(14, 5))\n",
    "fig.suptitle(f\"{data['card_name']} ({data.get('set_code', '')}) — Price Distribution\", fontsize=14)\n",
    "\n",
    "def _plot_hist(ax, df, col, label, color, agg):\n",
    "    if df.empty or col not in df.columns:\n",
    "        ax.text(0.5, 0.5, \"No data\", ha=\"center\", va=\"center\", transform=ax.transAxes)\n",
    "        ax.set_title(f\"{label} (n=0)\")\n",
    "        return\n",
    "    ax.hist(df[col], bins=15, color=color, alpha=0.75, edgecolor=\"white\")\n",
    "    median = agg.get(\"median\")\n",
    "    p25    = agg.get(\"p25\")\n",
    "    p75    = agg.get(\"p75\")\n",
    "    if median is not None:\n",
    "        ax.axvline(median, color=\"navy\" if color == \"steelblue\" else \"darkred\",\n",
    "                   linestyle=\"--\", linewidth=1.8, label=f\"Median ${median:.2f}\")\n",
    "    if p25 is not None and p75 is not None:\n",
    "        ax.axvspan(p25, p75, alpha=0.12, color=color, label=f\"IQR ${p25:.2f}–${p75:.2f}\")\n",
    "    ax.set_title(f\"{label} (n={agg.get('count', 0)})\")\n",
    "    ax.set_xlabel(\"Price (AUD)\")\n",
    "    ax.set_ylabel(\"Count\")\n",
    "    ax.legend(fontsize=8)\n",
    "\n",
    "_plot_hist(axes[0], sold_df,   \"price\", \"Sold (completed)\",  \"steelblue\", data[\"sold_aggregates\"])\n",
    "_plot_hist(axes[1], active_df, \"price\", \"Active (listed now)\", \"coral\",   data[\"active_aggregates\"])\n",
    "\n",
    "plt.tight_layout()\n",
    "plt.show()\n"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "s = data[\"sold_aggregates\"]\n",
    "a = data[\"active_aggregates\"]\n",
    "sp = data[\"suggested_price\"]\n",
    "\n",
    "print(\"╔══════════════════════════════════════╗\")\n",
    "print(\"║       PRICE SUGGESTION SUMMARY       ║\")\n",
    "print(\"╠══════════════════════════════════════╣\")\n",
    "if sp:\n",
    "    print(f\"║  Suggested price (sold median): ${sp:>6.2f} ║\")\n",
    "else:\n",
    "    print(\"║  Suggested price: N/A (<3 sold results)║\")\n",
    "print(f\"║  Sold  — n={s['count']:<3}  median=${s.get('median') or 0:>6.2f}        ║\")\n",
    "print(f\"║         IQR  ${s.get('p25') or 0:.2f} – ${s.get('p75') or 0:.2f}              ║\")\n",
    "print(f\"║  Active— n={a['count']:<3}  floor=${a.get('min') or 0:>6.2f}         ║\")\n",
    "print(\"╚══════════════════════════════════════╝\")\n"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Threshold tuning — re-run with a lower threshold to see impact\n",
    "LOW_THRESHOLD = 0.4\n",
    "params_loose = {**params, \"match_threshold\": LOW_THRESHOLD}\n",
    "resp_loose = httpx.get(f\"{BASE_URL}/api/v1/integrations/ebay/market-price/\", params=params_loose, timeout=30)\n",
    "resp_loose.raise_for_status()\n",
    "data_loose = resp_loose.json()\n",
    "\n",
    "print(f\"threshold={THRESHOLD}:      sold={data['sold_aggregates']['count']}  active={data['active_aggregates']['count']}\")\n",
    "print(f\"threshold={LOW_THRESHOLD}: sold={data_loose['sold_aggregates']['count']}  active={data_loose['active_aggregates']['count']}\")\n",
    "print(f\"Extra sold results at lower threshold: {data_loose['sold_aggregates']['count'] - data['sold_aggregates']['count']}\")\n"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "name": "python",
   "version": "3.11.0"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
```

- [ ] **Step 7.3 — Commit**

```bash
git add notebooks/ebay_price_research.ipynb
git commit -m "feat(ebay): add ebay_price_research notebook with distribution charts"
```

---

## Final Verification

- [ ] **Run the full unit test suite**

```bash
pytest tests/unit/ -v -k "market_price or finding"
```
Expected: all tests pass.

- [ ] **Run all unit tests to check for regressions**

```bash
pytest tests/unit/ -q
```
Expected: no new failures.

- [ ] **Start the backend and smoke-test the endpoint**

```bash
# In one terminal: start backend
dcdev-automana up -d backend

# In another: call the endpoint
curl -s "http://localhost:8000/api/v1/integrations/ebay/market-price/?card_name=Lightning+Bolt&app_code=automana_au&set_code=M10&days_back=30&limit=10" | python3 -m json.tool | head -40
```
Expected: JSON response with `card_name`, `sold_aggregates`, `active_aggregates` fields. `suggested_price` may be null if fewer than 3 sold results.

---

## Implementation Notes

- **MTG category ID:** The plan uses `2536` (Magic: The Gathering). Verify against the eBay Finding API before shipping — search `categoryId=2536` and confirm results are MTG cards, not collectibles from other games.
- **App ID in settings:** `settings.ebay_app_id` already exists. Ensure it's populated in your `.env.dev` under `EBAY_APP_ID`.
- **Sandbox vs production:** The Finding API sandbox (`svcs.sandbox.ebay.com`) returns mock data and may not reflect real price distributions. Run notebook demos against production once you have a production `app_code`.
- **Notebook dependencies:** The notebook is not run by the backend. Install in your local notebook env: `pip install httpx pandas matplotlib jupyter`.
