# Promo Type Faceted Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a multi-select dropdown to the search sidebar that shows the promo types present in the current results and narrows the search when any are selected.

**Architecture:** The backend `search()` method runs a second lightweight SQL query (same WHERE conditions, `LATERAL unnest`) to compute `promo_type_facets`, which flows up through the service layer into a new `facets` field on `PaginatedResponse`. The frontend reads facets from page 1 of the infinite query, passes them to `SearchFilters`, and renders a `<details>/<summary>` collapsible dropdown with checkboxes.

**Tech Stack:** Python (asyncpg, FastAPI, Pydantic v2, dataclasses), TypeScript (React 18, TanStack Router v1, TanStack Query v5, Zod), Vitest + React Testing Library, pytest + AsyncMock.

---

## File Map

| File | Change |
|------|--------|
| `src/automana/database/SQL/schemas/02_card_schema.sql` | Add GIN index on `v_card_versions_complete.promo_types` |
| `src/automana/core/services/card_catalog/card_service.py` | `CardSearchResult` gets `promo_type_facets`; `search_cards` threads param and facets |
| `src/automana/api/schemas/StandardisedQueryResponse.py` | `PaginatedResponse` gets `facets: Optional[Dict[str, List[str]]] = None` |
| `src/automana/core/repositories/card_catalog/card_repository.py` | `search()` gets `promo_type` filter + facet query |
| `src/automana/api/dependancies/query_deps.py` | `card_search_params` adds `promo_type: Optional[List[str]]` |
| `src/automana/api/routers/mtg/card_reference.py` | `list_cards` passes `facets={"promo_types": ...}` |
| `src/frontend/src/features/cards/types.ts` | `CardSearchParams` adds `promoTypes?: string[]` |
| `src/frontend/src/features/cards/api.ts` | Serialize `promoTypes`; read `body.facets` |
| `src/frontend/src/routes/search.tsx` | `searchSchema` adds `promoTypes`; extract facets; pass to `SearchFilters` |
| `src/frontend/src/features/cards/components/SearchFilters.tsx` | Promo type dropdown section |
| `src/frontend/src/features/cards/components/SearchFilters.module.css` | Dropdown styles |

---

### Task 1: GIN index on `v_card_versions_complete.promo_types`

**Files:**
- Modify: `src/automana/database/SQL/schemas/02_card_schema.sql` (after line 598, after the `color_identity` GIN index)

The materialized view already carries `promo_types text[]`. Without a GIN index the facet query does a full scan. Add the index so `&&` array-overlap and `LATERAL unnest` are efficient.

- [ ] **Step 1: Add the index**

Open `src/automana/database/SQL/schemas/02_card_schema.sql`. Find this existing line (~line 598):

```sql
CREATE INDEX idx_v_card_versions_complete_colors ON card_catalog.v_card_versions_complete USING GIN (color_identity);
```

Add directly below it:

```sql
CREATE INDEX IF NOT EXISTS idx_v_card_versions_complete_promo_types
    ON card_catalog.v_card_versions_complete USING GIN (promo_types);
```

- [ ] **Step 2: Verify**

```bash
grep "idx_v_card_versions_complete_promo_types" src/automana/database/SQL/schemas/02_card_schema.sql
```

Expected: one matching line.

- [ ] **Step 3: Commit**

```bash
git add src/automana/database/SQL/schemas/02_card_schema.sql
git commit -m "perf(card_catalog): GIN index on v_card_versions_complete.promo_types"
```

---

### Task 2: `CardSearchResult` + `PaginatedResponse` model changes

**Files:**
- Modify: `src/automana/core/services/card_catalog/card_service.py` (line 1–26)
- Modify: `src/automana/api/schemas/StandardisedQueryResponse.py` (line 24–25)
- Create: `tests/unit/core/services/card_catalog/test_card_search_result_facets.py`
- Create: `tests/unit/api/schemas/test_paginated_response_facets.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/core/services/card_catalog/test_card_search_result_facets.py`:

```python
"""Unit tests: CardSearchResult carries promo_type_facets."""
import pytest
from automana.core.services.card_catalog.card_service import CardSearchResult

pytestmark = pytest.mark.unit


def test_card_search_result_default_facets():
    result = CardSearchResult(cards=[], total_count=0)
    assert result.promo_type_facets == []


def test_card_search_result_with_facets():
    result = CardSearchResult(cards=[], total_count=0, promo_type_facets=["buyabox", "prerelease"])
    assert result.promo_type_facets == ["buyabox", "prerelease"]
```

Create `tests/unit/api/schemas/test_paginated_response_facets.py`:

```python
"""Unit tests: PaginatedResponse carries facets field."""
import pytest
from automana.api.schemas.StandardisedQueryResponse import PaginatedResponse, PaginationInfo

pytestmark = pytest.mark.unit


def test_paginated_response_facets_defaults_none():
    resp = PaginatedResponse[str](
        data=[],
        pagination=PaginationInfo(limit=20, offset=0, total_count=0, has_next=False, has_previous=False),
    )
    assert resp.facets is None


def test_paginated_response_facets_field():
    resp = PaginatedResponse[str](
        data=[],
        pagination=PaginationInfo(limit=20, offset=0, total_count=0, has_next=False, has_previous=False),
        facets={"promo_types": ["prerelease", "buyabox"]},
    )
    assert resp.facets == {"promo_types": ["prerelease", "buyabox"]}
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/unit/core/services/card_catalog/test_card_search_result_facets.py tests/unit/api/schemas/test_paginated_response_facets.py -v
```

Expected: `AttributeError` or `TypeError` — `promo_type_facets` / `facets` fields do not exist yet.

- [ ] **Step 3: Add `promo_type_facets` to `CardSearchResult`**

In `src/automana/core/services/card_catalog/card_service.py`, change line 1:

```python
from dataclasses import dataclass
```

to:

```python
from dataclasses import dataclass, field
```

Then change `CardSearchResult` (lines 22–25):

```python
@dataclass
class CardSearchResult:
    cards: List[BaseCard]
    total_count: int
    promo_type_facets: List[str] = field(default_factory=list)
```

- [ ] **Step 4: Add `facets` to `PaginatedResponse`**

In `src/automana/api/schemas/StandardisedQueryResponse.py`, change `PaginatedResponse` (lines 24–25):

```python
class PaginatedResponse(ApiResponse[List[DataT]], Generic[DataT]):
    pagination: PaginationInfo
    facets: Optional[Dict[str, List[str]]] = None
```

The `Dict` import is already present on line 1.

- [ ] **Step 5: Run tests — verify they pass**

```bash
python -m pytest tests/unit/core/services/card_catalog/test_card_search_result_facets.py tests/unit/api/schemas/test_paginated_response_facets.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/card_catalog/card_service.py \
        src/automana/api/schemas/StandardisedQueryResponse.py \
        tests/unit/core/services/card_catalog/test_card_search_result_facets.py \
        tests/unit/api/schemas/test_paginated_response_facets.py
git commit -m "feat(card_catalog): CardSearchResult.promo_type_facets + PaginatedResponse.facets"
```

---

### Task 3: `card_repository.search()` — promo_type filter + facet query

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py` (method `search`, lines 155–331)
- Create: `tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py`

The existing `search()` already builds `conditions`, `values`, `where_clause`, and a separate `count_query` reusing `count_values = values[:-2]`. We follow the same pattern for the facet query.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py`:

```python
"""Unit tests: card_repository.search() promo_type filter and facets."""
import pytest
from unittest.mock import AsyncMock, call
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository

pytestmark = pytest.mark.unit

_CARD_ROW = {
    "card_version_id": "aaaaaaaa-0000-0000-0000-000000000000",
    "card_name": "Ragavan",
    "rarity_name": "mythic",
    "set_name": "Modern Horizons 2",
    "set_code": "mh2",
    "cmc": 1,
    "oracle_text": "...",
    "digital": False,
    "released_at": "2021-06-18",
    "image_normal": None,
}


def _make_repo(cards_rows, count_rows, facet_rows):
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(side_effect=[cards_rows, count_rows, facet_rows])
    return repo


@pytest.mark.asyncio
async def test_search_includes_promo_type_filter_in_sql():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": ["prerelease"]}])
    await repo.search(promo_type=["prerelease"])
    main_call_sql = repo.execute_query.call_args_list[0][0][0]
    assert "v.promo_types && $" in main_call_sql


@pytest.mark.asyncio
async def test_search_returns_promo_type_facets():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": ["buyabox", "prerelease"]}])
    result = await repo.search()
    assert result["promo_type_facets"] == ["buyabox", "prerelease"]


@pytest.mark.asyncio
async def test_search_returns_empty_facets_when_none():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": None}])
    result = await repo.search()
    assert result["promo_type_facets"] == []


@pytest.mark.asyncio
async def test_search_facet_query_uses_lateral_unnest():
    repo = _make_repo([], [{"total_count": 0}], [{"promo_type_facets": []}])
    await repo.search()
    facet_call_sql = repo.execute_query.call_args_list[2][0][0]
    assert "LATERAL unnest" in facet_call_sql
    assert "promo_type_facets" in facet_call_sql
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py -v
```

Expected: `AssertionError` or `StopIteration` — `execute_query` is only called twice (main + count), facet call doesn't exist yet, and `promo_type` param doesn't exist.

- [ ] **Step 3: Add `promo_type` parameter and filter condition**

In `src/automana/core/repositories/card_catalog/card_repository.py`, change the `search()` signature (line 155–173) to add `promo_type`:

```python
async def search(
        self,
        name: Optional[str] = None,
        color: Optional[str] = None,
        rarity: Optional[str] = None,
        set_name: Optional[str] = None,
        mana_cost: Optional[int] = None,
        digital: Optional[bool] = None,
        card_type: Optional[str] = None,
        released_after: Optional[str] = None,
        released_before: Optional[str] = None,
        oracle_text: Optional[str] = None,
        format: Optional[str] = None,
        layout: Optional[str] = None,
        promo_type: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: Optional[str] = "card_name",
        sort_order: Optional[str] = "asc",
) -> dict[str, Any]:
```

After the `layout` block (ending around line 267, just before `where_clause` is built), add:

```python
        if promo_type:
            # && = array overlap: card has ANY of the selected promo types
            conditions.append(f"v.promo_types && ${counter}")
            values.append(promo_type)
            counter += 1
```

- [ ] **Step 4: Add the facet query and return `promo_type_facets`**

In `search()`, find the end of the method where `return {"cards": cards, "total_count": total_count}` is (around line 328). Replace it with:

```python
        # Facet query — same WHERE conditions as count_query, with LATERAL unnest on promo_types.
        # count_values strips the trailing limit/offset values (values[:-2]).
        facet_query = f"""
            SELECT array_agg(DISTINCT pt ORDER BY pt) AS promo_type_facets
            FROM card_catalog.v_card_versions_complete v
            JOIN card_catalog.sets s ON s.set_id = v.set_id
            CROSS JOIN LATERAL unnest(v.promo_types) AS t(pt)
            {where_clause}
        """
        facet_result = await self.execute_query(facet_query, tuple(count_values))
        promo_type_facets = (
            (facet_result[0]["promo_type_facets"] or []) if facet_result else []
        )
        return {
            "cards": cards,
            "total_count": total_count,
            "promo_type_facets": promo_type_facets,
        }
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python -m pytest tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py \
        tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py
git commit -m "feat(card_catalog): promo_type filter and facet query in card_repository.search()"
```

---

### Task 4: Service + dependency + router wiring

**Files:**
- Modify: `src/automana/core/services/card_catalog/card_service.py` (function `search_cards`, lines 133–228)
- Modify: `src/automana/api/dependancies/query_deps.py` (function `card_search_params`, lines 86–130)
- Modify: `src/automana/api/routers/mtg/card_reference.py` (function `list_cards`, lines 194–227)
- Create: `tests/unit/core/services/card_catalog/test_card_service_search_promo.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/core/services/card_catalog/test_card_service_search_promo.py`:

```python
"""Unit tests: search_cards threads promo_type and surfaces promo_type_facets."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from automana.core.services.card_catalog.card_service import search_cards

pytestmark = pytest.mark.unit

_RAW = {
    "cards": [],
    "total_count": 0,
    "promo_type_facets": ["buyabox", "prerelease"],
}


@pytest.mark.asyncio
async def test_search_cards_forwards_promo_type_facets():
    repo = MagicMock()
    repo.search = AsyncMock(return_value=_RAW)
    with patch("automana.core.services.card_catalog.card_service.get_from_cache", return_value=None), \
         patch("automana.core.services.card_catalog.card_service.set_to_cache", new_callable=AsyncMock):
        result = await search_cards(card_repository=repo, promo_type=["buyabox"])
    repo.search.assert_called_once()
    call_kwargs = repo.search.call_args.kwargs
    assert call_kwargs.get("promo_type") == ["buyabox"]
    assert result.promo_type_facets == ["buyabox", "prerelease"]


@pytest.mark.asyncio
async def test_search_cards_facets_in_cache():
    repo = MagicMock()
    repo.search = AsyncMock(return_value=_RAW)
    captured_cache = {}

    async def fake_set(key, data, **kw):
        captured_cache.update(data)

    with patch("automana.core.services.card_catalog.card_service.get_from_cache", return_value=None), \
         patch("automana.core.services.card_catalog.card_service.set_to_cache", side_effect=fake_set):
        await search_cards(card_repository=repo)

    assert "promo_type_facets" in captured_cache
    assert captured_cache["promo_type_facets"] == ["buyabox", "prerelease"]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/unit/core/services/card_catalog/test_card_service_search_promo.py -v
```

Expected: `TypeError` — `search_cards` does not accept `promo_type` yet.

- [ ] **Step 3: Update `search_cards` service function**

In `src/automana/core/services/card_catalog/card_service.py`, add `promo_type` to the `search_cards` signature (after `layout` param, around line 151):

```python
async def search_cards(card_repository: CardReferenceRepository
                   , name: Optional[str] = None
                   , color: Optional[str] = None
                   , rarity: Optional[str] = None
                   , card_id: Optional[UUID] = None
                   , released_after: Optional[datetime] = None
                   , released_before: Optional[datetime] = None
                   , set_name: Optional[str] = None
                   , mana_cost: Optional[int] = None
                   , digital: Optional[bool] = None
                   , card_type: Optional[str] = None
                   , oracle_text: Optional[str] = None
                   , format: Optional[str] = None
                   , layout: Optional[str] = None
                   , promo_type: Optional[List[str]] = None
                   # Pagination
                   , limit: int = 100
                   , offset: int = 0
                   , sort_by: str = "name"
                   , sort_order: str = "asc"
                   ) -> CardSearchResult:
```

Add `promo_type` to the `params` dict used for cache key hashing (around line 159):

```python
        params = {
            "name": name,
            "color": color,
            "rarity": rarity,
            "card_id": str(card_id) if card_id else None,
            "released_after": str(released_after) if released_after else None,
            "released_before": str(released_before) if released_before else None,
            "set_name": set_name,
            "mana_cost": mana_cost,
            "digital": digital,
            "card_type": card_type,
            "oracle_text": oracle_text,
            "format": format,
            "layout": layout,
            "promo_type": promo_type,
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
```

Update the cache read path (around line 184):

```python
        cached = await get_from_cache(cache_key)
        if cached is not None:
            return CardSearchResult(
                cards=[BaseCard.model_validate(c) for c in cached["cards"]],
                total_count=cached["total_count"],
                promo_type_facets=cached.get("promo_type_facets", []),
            )
```

Pass `promo_type` to the repository call (around line 197):

```python
            raw = await card_repository.search(name=name,
                                               color=color,
                                               rarity=rarity,
                                               set_name=set_name,
                                               mana_cost=mana_cost,
                                               digital=digital,
                                               released_after=released_after,
                                               released_before=released_before,
                                               oracle_text=oracle_text,
                                               format=format,
                                               layout=layout,
                                               promo_type=promo_type,
                                               limit=limit,
                                               offset=offset,
                                               sort_by=sort_by,
                                               card_type=card_type,
                                               sort_order=sort_order)
```

Read `promo_type_facets` from the raw result and build `CardSearchResult` (around line 212):

```python
            promo_type_facets = raw.get("promo_type_facets", [])
            result = CardSearchResult(
                cards=[BaseCard.model_validate(card) for card in cards],
                total_count=total_count,
                promo_type_facets=promo_type_facets,
            )
```

Update the cache write (around line 219):

```python
        cache_data = {
            "cards": [c.model_dump() for c in result.cards],
            "total_count": result.total_count,
            "promo_type_facets": result.promo_type_facets,
        }
```

- [ ] **Step 4: Add `promo_type` to `card_search_params` dependency**

In `src/automana/api/dependancies/query_deps.py`, add to `card_search_params` parameters (after `layout`, around line 105):

```python
    promo_type: Optional[List[str]] = Query(None, description="Filter by promo type (repeatable: ?promo_type=prerelease&promo_type=buyabox)"),
```

Add to the return dict (after `"layout": layout`):

```python
    return {
        "name": search_name,
        "set_name": set_name,
        "card_type": card_type,
        "rarity": rarity,
        "mana_cost": mana_cost,
        "color": color,
        "card_id": card_id,
        "digital": digital,
        "card_type": card_type,
        "oracle_text": oracle_text,
        "format": format,
        "layout": layout,
        "promo_type": promo_type,
    }
```

- [ ] **Step 5: Pass facets in the router response**

In `src/automana/api/routers/mtg/card_reference.py`, update `list_cards` (around line 214):

```python
        return PaginatedResponse[BaseCard](
            data=cards,
            pagination=PaginationInfo(
                limit=pagination.limit,
                offset=pagination.offset,
                total_count=total_count,
                has_next=len(cards) == pagination.limit,
                has_previous=pagination.offset > 0,
            ),
            facets={"promo_types": result.promo_type_facets},
        )
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
python -m pytest tests/unit/core/services/card_catalog/test_card_service_search_promo.py -v
```

Expected: 2 tests PASS.

Run all backend unit tests to check for regressions:

```bash
python -m pytest tests/unit/ -v --tb=short
```

Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add src/automana/core/services/card_catalog/card_service.py \
        src/automana/api/dependancies/query_deps.py \
        src/automana/api/routers/mtg/card_reference.py \
        tests/unit/core/services/card_catalog/test_card_service_search_promo.py
git commit -m "feat(card_catalog): wire promo_type filter and facets through service/dep/router"
```

---

### Task 5: Frontend — types, API serialization, route schema

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts`
- Modify: `src/frontend/src/features/cards/api.ts`
- Modify: `src/frontend/src/routes/search.tsx`
- Create: `src/frontend/src/features/cards/__tests__/api.promo.test.ts`

- [ ] **Step 1: Write failing tests**

Create `src/frontend/src/features/cards/__tests__/api.promo.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { server } from '../../../mocks/server'
import { http, HttpResponse } from 'msw'
import { cardInfiniteSearchQueryOptions } from '../api'
import { QueryClient } from '@tanstack/react-query'

const PROMO_RESPONSE = {
  success: true,
  data: [],
  pagination: { limit: 20, offset: 0, total_count: 0, has_next: false, has_previous: false },
  facets: { promo_types: ['buyabox', 'prerelease'] },
}

describe('cardInfiniteSearchQueryOptions — promo type', () => {
  let capturedUrl: string

  beforeEach(() => {
    capturedUrl = ''
    server.use(
      http.get('/api/catalog/mtg/card-reference/', ({ request }) => {
        capturedUrl = request.url
        return HttpResponse.json(PROMO_RESPONSE)
      })
    )
  })

  it('serializes promoTypes as repeated promo_type params', async () => {
    const qc = new QueryClient()
    const opts = cardInfiniteSearchQueryOptions({ promoTypes: ['buyabox', 'prerelease'] })
    await qc.fetchInfiniteQuery({ ...opts, initialPageParam: 0 })
    const url = new URL(capturedUrl)
    expect(url.searchParams.getAll('promo_type')).toEqual(['buyabox', 'prerelease'])
  })

  it('reads facets.promo_types from response', async () => {
    const qc = new QueryClient()
    const opts = cardInfiniteSearchQueryOptions({})
    const result = await qc.fetchInfiniteQuery({ ...opts, initialPageParam: 0 })
    expect(result.pages[0].facets?.promo_types).toEqual(['buyabox', 'prerelease'])
  })
})
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd src/frontend && npx vitest run src/features/cards/__tests__/api.promo.test.ts
```

Expected: type errors and test failures — `promoTypes` not on `CardSearchParams`, `facets` not returned from the query fn.

- [ ] **Step 3: Update `CardSearchParams` in types.ts**

In `src/frontend/src/features/cards/types.ts`, update `CardSearchParams`:

```typescript
export interface CardSearchParams {
  q?: string
  set?: string
  rarity?: string
  finish?: string
  layout?: string
  minPrice?: number
  maxPrice?: number
  promoTypes?: string[]
}
```

- [ ] **Step 4: Update `cardInfiniteSearchQueryOptions` in api.ts**

In `src/frontend/src/features/cards/api.ts`, add `promoTypes` serialization and `facets` in the return. Replace the existing `cardInfiniteSearchQueryOptions` function:

```typescript
export function cardInfiniteSearchQueryOptions(params: Omit<CardSearchParams, 'page'>) {
  return infiniteQueryOptions({
    queryKey: ['cards', 'search', params],
    queryFn: async ({ pageParam = 0 }) => {
      const token = useAuthStore.getState().token
      const qs = new URLSearchParams()
      if (params.q)        qs.set('q', params.q)
      if (params.set)      qs.set('set', params.set)
      if (params.rarity)   qs.set('rarity', params.rarity)
      if (params.finish)   qs.set('finish', params.finish)
      if (params.layout)   qs.set('layout', params.layout)
      if (params.minPrice != null) qs.set('min_price', String(params.minPrice))
      if (params.maxPrice != null) qs.set('max_price', String(params.maxPrice))
      params.promoTypes?.forEach(pt => qs.append('promo_type', pt))
      qs.set('limit', '20')
      qs.set('offset', String(pageParam))

      const res = await fetch(`/api/catalog/mtg/card-reference/?${qs}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })

      if (!res.ok) throw new Error(`API ${res.status}`)
      const body = await res.json()

      return {
        cards: body.data ?? [],
        pagination: body.pagination,
        facets: (body.facets as { promo_types?: string[] } | null) ?? null,
      }
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.pagination?.has_next
        ? lastPage.pagination.offset + lastPage.pagination.limit
        : undefined,
  })
}
```

- [ ] **Step 5: Update `search.tsx` — schema + facet extraction**

In `src/frontend/src/routes/search.tsx`, update `searchSchema`:

```typescript
const searchSchema = z.object({
  q:          z.string().optional(),
  set:        z.string().optional(),
  rarity:     z.string().optional(),
  finish:     z.string().optional(),
  layout:     z.string().optional(),
  minPrice:   z.number().optional(),
  maxPrice:   z.number().optional(),
  promoTypes: z.array(z.string()).optional(),
})
```

In `SearchPage`, extract `promoTypeFacets` and pass to `SearchFilters`:

```typescript
function SearchPage() {
  const search = Route.useSearch()
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = useInfiniteQuery(
    cardInfiniteSearchQueryOptions(search)
  )

  const cards = data?.pages?.flatMap(p => p.cards) ?? []
  const total = data?.pages?.[0]?.pagination?.total_count ?? 0
  const promoTypeFacets = data?.pages?.[0]?.facets?.promo_types ?? []

  return (
    <AppShell active="collection">
      <TopBar
        title="Search"
        subtitle={search.q ? `results for "${search.q}"` : 'all cards'}
      />
      <div className={styles.layout}>
        <SearchFilters params={search} promoTypeFacets={promoTypeFacets} />
        <SearchResults
          cards={cards}
          total={total}
          fetchNextPage={fetchNextPage}
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
        />
      </div>
    </AppShell>
  )
}
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
cd src/frontend && npx vitest run src/features/cards/__tests__/api.promo.test.ts
```

Expected: 2 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/features/cards/types.ts \
        src/frontend/src/features/cards/api.ts \
        src/frontend/src/routes/search.tsx \
        src/frontend/src/features/cards/__tests__/api.promo.test.ts
git commit -m "feat(frontend): promoTypes in CardSearchParams, api serialization, and route schema"
```

---

### Task 6: `SearchFilters` — promo type dropdown

**Files:**
- Modify: `src/frontend/src/features/cards/components/SearchFilters.tsx`
- Modify: `src/frontend/src/features/cards/components/SearchFilters.module.css`
- Create: `src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SearchFilters } from '../SearchFilters'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

const BASE_PARAMS = { q: 'ragavan' }

describe('SearchFilters — promo type dropdown', () => {
  it('hides promo section when promoTypeFacets is empty', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} />)
    expect(screen.queryByText(/promo type/i)).toBeNull()
  })

  it('renders promo type section when facets present', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={['buyabox', 'prerelease']} />)
    expect(screen.getByText(/promo type/i)).toBeTruthy()
  })

  it('uses display label for known promo type', () => {
    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={['buyabox']} />)
    // open the dropdown
    fireEvent.click(screen.getByRole('group').querySelector('summary')!)
    expect(screen.getByText('Buy a Box')).toBeTruthy()
  })

  it('shows selection count in summary when promoTypes selected', () => {
    render(
      <SearchFilters
        params={{ ...BASE_PARAMS, promoTypes: ['buyabox', 'prerelease'] }}
        promoTypeFacets={['buyabox', 'prerelease']}
      />
    )
    expect(screen.getByText(/2 selected/i)).toBeTruthy()
  })

  it('calls navigate with toggled promoTypes on checkbox change', () => {
    const mockNavigate = vi.fn()
    vi.mocked(require('@tanstack/react-router').useNavigate).mockReturnValue(() => mockNavigate)

    render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={['prerelease']} />)
    fireEvent.click(screen.getByRole('group').querySelector('summary')!)
    fireEvent.click(screen.getByRole('checkbox'))
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({ search: expect.any(Function) })
    )
  })
})
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd src/frontend && npx vitest run src/features/cards/components/__tests__/SearchFilters.promo.test.tsx
```

Expected: `TypeError` — `SearchFilters` does not accept `promoTypeFacets` prop yet.

- [ ] **Step 3: Add CSS styles for the dropdown**

In `src/frontend/src/features/cards/components/SearchFilters.module.css`, append:

```css
.promoDropdown { margin-top: 6px; }
.promoSummary { font-family: var(--font-mono); font-size: 11px; color: var(--hd-muted); cursor: pointer; list-style: none; display: flex; justify-content: space-between; align-items: center; user-select: none; }
.promoSummary::-webkit-details-marker { display: none; }
.promoList { margin-top: 8px; max-height: 180px; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
```

- [ ] **Step 4: Add `PROMO_TYPE_LABELS`, `promoLabel`, and the dropdown section to `SearchFilters.tsx`**

Replace the entire contents of `src/frontend/src/features/cards/components/SearchFilters.tsx` with:

```typescript
// src/frontend/src/features/cards/components/SearchFilters.tsx
import { useNavigate } from '@tanstack/react-router'
import type { CardSearchParams } from '../types'
import { SearchBarWithSuggestions } from './SearchBarWithSuggestions'
import styles from './SearchFilters.module.css'

const RARITIES = ['common', 'uncommon', 'rare', 'mythic'] as const
const FINISHES = ['non-foil', 'foil', 'etched'] as const
const LAYOUTS = ['normal', 'token', 'transform', 'saga', 'adventure'] as const

const PROMO_TYPE_LABELS: Record<string, string> = {
  arenaleague:        'Arena League',
  boosterfun:         'Booster Fun',
  boxtopper:          'Box Topper',
  brawldeck:          'Brawl Deck',
  bundle:             'Bundle',
  buyabox:            'Buy a Box',
  convention:         'Convention',
  datestamped:        'Datestamped',
  draftweekend:       'Draft Weekend',
  duels:              'Duels',
  event:              'Event',
  fnm:                'Friday Night Magic',
  gameday:            'Game Day',
  gateway:            'Gateway',
  giftbox:            'Gift Box',
  gilded:             'Gilded',
  instore:            'In-Store',
  intropack:          'Intro Pack',
  jpwalker:           'JP Planeswalker',
  judgegift:          'Judge Gift',
  league:             'League',
  mediainsert:        'Media Insert',
  neonink:            'Neon Ink',
  openhouse:          'Open House',
  planeswalkerdeck:   'Planeswalker Deck',
  playerrewards:      'Player Rewards',
  playpromo:          'Play Promo',
  premiumdeck:        'Premium Deck',
  prerelease:         'Prerelease',
  promopack:          'Promo Pack',
  release:            'Release',
  serialized:         'Serialized',
  setpromo:           'Set Promo',
  starterdeck:        'Starter Deck',
  stepandcompleat:    'Step and Compleat',
  store:              'Store',
  textured:           'Textured',
  themepack:          'Theme Pack',
  tourney:            'Tourney',
  wizardsplaynetwork: 'Wizards Play Network',
}

function promoLabel(code: string): string {
  return PROMO_TYPE_LABELS[code] ?? code.charAt(0).toUpperCase() + code.slice(1)
}

interface SearchFiltersProps {
  params: CardSearchParams
  promoTypeFacets: string[]
}

export function SearchFilters({ params, promoTypeFacets }: SearchFiltersProps) {
  const navigate = useNavigate({ from: '/search' })

  function update(patch: Partial<CardSearchParams>) {
    navigate({ search: (prev) => ({ ...prev, ...patch }) })
  }

  function togglePromoType(pt: string) {
    const current = params.promoTypes ?? []
    const next = current.includes(pt) ? current.filter(x => x !== pt) : [...current, pt]
    update({ promoTypes: next.length > 0 ? next : undefined })
  }

  const selectedPromoCount = params.promoTypes?.length ?? 0

  return (
    <aside className={styles.filters}>
      <div className={styles.searchWrapper}>
        <SearchBarWithSuggestions placeholder="" />
      </div>

      <div className={styles.header}>
        <span className={styles.title}>Filters</span>
        <button className={styles.clear} onClick={() => navigate({ search: { q: params.q } })}>
          clear
        </button>
      </div>

      <section className={styles.group}>
        <div className={styles.groupLabel}>Rarity</div>
        {RARITIES.map((r) => (
          <label key={r} className={styles.checkRow}>
            <input
              type="checkbox"
              checked={params.rarity === r}
              onChange={(e) => update({ rarity: e.target.checked ? r : undefined })}
            />
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <span className={[styles.rarityDot, styles[r]].join(' ')} />
              {r.charAt(0).toUpperCase() + r.slice(1)}
            </span>
          </label>
        ))}
      </section>

      <section className={styles.group}>
        <div className={styles.groupLabel}>Finish</div>
        <div className={styles.finishGrid}>
          {FINISHES.map((f) => (
            <button
              key={f}
              className={[styles.finishBtn, params.finish === f ? styles.finishActive : ''].join(' ')}
              onClick={() => update({ finish: params.finish === f ? undefined : f })}
            >
              {f}
            </button>
          ))}
        </div>
      </section>

      <section className={styles.group}>
        <div className={styles.groupLabel}>Layout</div>
        <div className={styles.finishGrid}>
          {LAYOUTS.map((l) => (
            <button
              key={l}
              className={[styles.finishBtn, params.layout === l ? styles.finishActive : ''].join(' ')}
              onClick={() => update({ layout: params.layout === l ? undefined : l })}
            >
              {l.charAt(0).toUpperCase() + l.slice(1)}
            </button>
          ))}
        </div>
      </section>

      {promoTypeFacets.length > 0 && (
        <section className={styles.group} role="group" aria-labelledby="promo-label">
          <div className={styles.groupLabel} id="promo-label">Promo type</div>
          <details className={styles.promoDropdown}>
            <summary className={styles.promoSummary}>
              <span>{selectedPromoCount > 0 ? `${selectedPromoCount} selected` : 'All types'}</span>
              <span aria-hidden="true">▾</span>
            </summary>
            <div className={styles.promoList}>
              {promoTypeFacets.map((pt) => (
                <label key={pt} className={styles.checkRow}>
                  <input
                    type="checkbox"
                    checked={params.promoTypes?.includes(pt) ?? false}
                    onChange={() => togglePromoType(pt)}
                  />
                  {promoLabel(pt)}
                </label>
              ))}
            </div>
          </details>
        </section>
      )}
    </aside>
  )
}
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd src/frontend && npx vitest run src/features/cards/components/__tests__/SearchFilters.promo.test.tsx
```

Expected: 5 tests PASS.

Run the full frontend test suite to catch regressions:

```bash
cd src/frontend && npx vitest run
```

Expected: no new failures (existing `SearchFilters` usage in `search.tsx` now passes `promoTypeFacets`).

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/cards/components/SearchFilters.tsx \
        src/frontend/src/features/cards/components/SearchFilters.module.css \
        src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx
git commit -m "feat(frontend): promo type facet dropdown in SearchFilters"
```

---

## Self-Review

**Spec coverage:**
- ✅ GIN index → Task 1
- ✅ Facet query (same WHERE, `LATERAL unnest`) → Task 3
- ✅ `&&` array overlap filter → Task 3
- ✅ `PaginatedResponse.facets` → Task 2
- ✅ `CardSearchResult.promo_type_facets` → Task 2
- ✅ Service threads `promo_type` + facets → Task 4
- ✅ `card_search_params` dep → Task 4
- ✅ Router passes `facets` → Task 4
- ✅ `promoTypes` in `CardSearchParams` → Task 5
- ✅ Repeated `promo_type` URL params → Task 5
- ✅ `facets.promo_types` read from response → Task 5
- ✅ `promoTypes` in `searchSchema` → Task 5
- ✅ Facets extracted + passed to `SearchFilters` → Task 5
- ✅ `PROMO_TYPE_LABELS` map + `promoLabel()` fallback → Task 6
- ✅ `<details>/<summary>` multi-select dropdown → Task 6
- ✅ Hidden when `promoTypeFacets` empty → Task 6
- ✅ Summary shows count when selected → Task 6

**Type consistency:**
- `promo_type_facets: List[str]` flows: repo dict → `CardSearchResult.promo_type_facets` → `facets={"promo_types": ...}` → `body.facets.promo_types` → `promoTypeFacets: string[]` prop. ✅
- `promo_type` param name: `Optional[List[str]]` in repo, service, and dep. FastAPI query param name `promo_type`. Frontend appends `qs.append('promo_type', pt)`. ✅

**No placeholders found.** ✅
