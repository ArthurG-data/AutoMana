# Card Search & Set Browser UI Refresh — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sort controls, simplify group-by, add color/type/price-trend/upcoming filters, and surface unreleased cards clearly in both card search and the set browser.

**Architecture:** Backend changes are minimal — `released_at` already reaches the query via SET JOIN but is missing from the Pydantic model; price sort is added via a LEFT JOIN to `pricing.mv_card_price_spark`; multi-color filtering is a one-liner loop change. All other new filters (price trend, upcoming toggle) are client-side memo filters applied to already-loaded results.

**Tech Stack:** FastAPI/Python backend (`card_repository.py`, `query_deps.py`, `card.py`), React 18 + TypeScript frontend (Vitest + React Testing Library), TanStack Query for server state.

---

## File Map

| File | Change |
|------|--------|
| `src/automana/core/models/card_catalog/card.py` | Add `released_at` to `BaseCard` |
| `src/automana/api/dependancies/query_deps.py` | Expand `color` → repeatable `colors[]` |
| `src/automana/core/repositories/card_catalog/card_repository.py` | Price sort via JOIN; multi-color loop; `released_at` in base_select already present |
| `src/frontend/src/features/cards/types.ts` | Narrow `CardGroupBy`; add `sort_by`, `sort_order`, `colors`, `card_type`, `released_at` |
| `src/frontend/src/features/cards/api.ts` | Forward new params to API |
| `src/frontend/src/features/cards/components/SearchFilters.tsx` | Sort section, simplified group-by, Color, Type, Price trend, Upcoming |
| `src/frontend/src/features/cards/components/SearchFilters.module.css` | Color pill styles, sort active style |
| `src/frontend/src/features/cards/components/SearchResults.tsx` | Price label logic; simplified `buildGroups` |
| `src/frontend/src/features/cards/components/SearchResults.module.css` | Add `.unreleased` amber class |
| `src/frontend/src/features/cards/components/SetCard.tsx` | Upcoming badge + gold border |
| `src/frontend/src/features/cards/components/SetCard.module.css` | Upcoming styles |
| `src/frontend/src/routes/search.tsx` | Narrow zod schema; local state for priceTrend / upcomingOnly; client-side filter memo |
| `tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py` | Extend for color/price sort |
| `src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx` | Extend for new sections |
| `src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx` | Add upcoming badge test |

---

## Task 1: Backend — add `released_at` to `BaseCard`

**Files:**
- Modify: `src/automana/core/models/card_catalog/card.py`
- Test: `tests/unit/core/models/card_catalog/test_create_card.py` (existing file, add one test)

`released_at` is already in the SQL `base_select` (line 592: `s.released_at`) but missing from the Pydantic model, so it's silently dropped in API responses.

- [ ] **Step 1: Write the failing test**

Create a new test file:

```python
# tests/unit/core/models/card_catalog/test_base_card_released_at.py
import pytest
from automana.core.models.card_catalog.card import BaseCard

pytestmark = pytest.mark.unit

def test_base_card_accepts_released_at():
    card = BaseCard(
        card_name="Ragavan",
        set_name="Modern Horizons 2",
        set_code="mh2",
        cmc=1,
        rarity_name="mythic",
        oracle_text="",
        digital=False,
        finish="non-foil",
        released_at="2021-06-18",
    )
    assert card.released_at == "2021-06-18"

def test_base_card_released_at_defaults_to_none():
    card = BaseCard(
        card_name="Ragavan",
        set_name="Modern Horizons 2",
        set_code="mh2",
        cmc=1,
        rarity_name="mythic",
        oracle_text="",
        digital=False,
        finish="non-foil",
    )
    assert card.released_at is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/arthur/projects/AutoMana && pytest tests/unit/core/models/card_catalog/test_base_card_released_at.py -v
```

Expected: `FAILED` — `BaseCard` does not accept `released_at`

- [ ] **Step 3: Add `released_at` to `BaseCard`**

In `src/automana/core/models/card_catalog/card.py`, add after the `spark` field (line 27):

```python
released_at: Optional[str] = Field(default=None, title="Set release date (ISO 8601, e.g. '2024-02-09')")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/arthur/projects/AutoMana && pytest tests/unit/core/models/card_catalog/test_base_card_released_at.py -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/models/card_catalog/card.py tests/unit/core/models/card_catalog/test_base_card_released_at.py
git commit -m "feat(backend): expose released_at in BaseCard model"
```

---

## Task 2: Backend — price sort via JOIN

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py` (lines ~531–573, ~543–547)
- Test: `tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py` (add tests)

Price data is fetched post-query via Redis/DB in `_fetch_prices_for_cards`. To support global sort-by-price, add a `LEFT JOIN pricing.mv_card_price_spark psp ON psp.card_version_id = v.card_version_id` and expose `psp.price AS sort_price` in `base_select`. Handle `sort_by='price'` as a special case in the ORDER BY logic.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py`:

```python
@pytest.mark.asyncio
async def test_search_sort_by_price_uses_psp_join():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": []}])
    await repo.search(sort_by="price", sort_order="asc")
    main_call_sql = repo.execute_query.call_args_list[0][0][0]
    assert "pricing.mv_card_price_spark" in main_call_sql
    assert "psp.price" in main_call_sql or "sort_price" in main_call_sql

@pytest.mark.asyncio
async def test_search_sort_by_price_desc_nulls_last():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": []}])
    await repo.search(sort_by="price", sort_order="desc")
    main_call_sql = repo.execute_query.call_args_list[0][0][0]
    assert "NULLS LAST" in main_call_sql
    assert "DESC" in main_call_sql
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana && pytest tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py::test_search_sort_by_price_uses_psp_join tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py::test_search_sort_by_price_desc_nulls_last -v
```

Expected: `FAILED`

- [ ] **Step 3: Add LEFT JOIN + sort_price to `from_clause` and `base_select`**

In `card_repository.py`, find `from_clause` (around line 542–547). Change it to:

```python
from_clause = (
    "FROM card_catalog.v_card_versions_complete v"
    " JOIN card_catalog.sets s ON s.set_id = v.set_id"
    " LEFT JOIN card_catalog.card_version_illustration cvi ON cvi.card_version_id = v.card_version_id"
    " LEFT JOIN pricing.mv_card_price_spark psp ON psp.card_version_id = v.card_version_id"
)
```

In `base_select` (around line 578–594), add `psp.price AS sort_price` before `{sv_col}`:

```python
base_select = f"""
        v.card_version_id,
        v.unique_card_id,
        v.card_name,
        v.rarity_name,
        v.set_name,
        v.set_code,
        v.cmc,
        v.oracle_text,
        v.promo_types,
        v.collector_number,
        v.is_digital AS digital,
        v.collector_number,
        v.promo_types,
        s.released_at,
        cvi.image_uris->>'normal' AS image_normal,
        psp.price AS sort_price
        {sv_col}"""
```

- [ ] **Step 4: Update ORDER BY logic to handle `sort_by='price'`**

In `card_repository.py`, find the `else` block that sets `_set_cols` and `_view_cols` for the non-text-search ORDER BY (around line 530). Replace **both** occurrences (non-collapse path ~line 530 and collapse outer_order path ~line 565) with the pattern below. The first occurrence (non-collapse ORDER BY):

```python
else:
    _set_cols = {"released_at"}
    _price_cols = {"price"}
    _view_cols = {"card_name", "cmc", "rarity_name", "set_name", "set_code"}
    safe_sort_order = "DESC" if (sort_order or "").upper() == "DESC" else "ASC"
    if sort_by in _set_cols:
        order_clause = f"ORDER BY s.{sort_by} {safe_sort_order}"
        collapse_order_clause = f"ORDER BY {sort_by} {safe_sort_order}"
    elif sort_by in _price_cols:
        order_clause = f"ORDER BY psp.price {safe_sort_order} NULLS LAST"
        collapse_order_clause = f"ORDER BY sort_price {safe_sort_order} NULLS LAST"
    else:
        safe_sort_by = sort_by if sort_by in _view_cols else "card_name"
        order_clause = f"ORDER BY v.{safe_sort_by} {safe_sort_order}"
        collapse_order_clause = f"ORDER BY {safe_sort_by} {safe_sort_order}"
```

The second occurrence (collapse outer_order ~line 565):

```python
else:
    _set_cols = {"released_at"}
    _price_cols = {"price"}
    _view_cols = {"card_name", "cmc", "rarity_name", "set_name", "set_code"}
    safe_sort_order = "DESC" if (sort_order or "").upper() == "DESC" else "ASC"
    if sort_by in _set_cols:
        outer_order = f"ORDER BY released_at {safe_sort_order}"
    elif sort_by in _price_cols:
        outer_order = f"ORDER BY sort_price {safe_sort_order} NULLS LAST"
    else:
        safe_sort_by = sort_by if sort_by in _view_cols else "card_name"
        outer_order = f"ORDER BY {safe_sort_by} {safe_sort_order}"
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/arthur/projects/AutoMana && pytest tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py -v
```

Expected: all tests `PASSED` (including pre-existing ones)

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py
git commit -m "feat(backend): add price sort via mv_card_price_spark LEFT JOIN"
```

---

## Task 3: Backend — expand `color` to multi-value `colors[]`

**Files:**
- Modify: `src/automana/api/dependancies/query_deps.py`
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py`
- Test: `tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py` (add test)

The backend currently accepts a single `color` string. Change to a repeatable list so `?color=Blue&color=Green` filters to cards containing both Blue AND Green.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py`:

```python
@pytest.mark.asyncio
async def test_search_multi_color_adds_condition_per_color():
    repo = _make_repo([_CARD_ROW], [{"total_count": 1}], [{"promo_type_facets": []}])
    await repo.search(colors=["Blue", "Green"])
    main_call_sql = repo.execute_query.call_args_list[0][0][0]
    # Two separate ANY conditions, one per color
    assert main_call_sql.count("= ANY(v.color_identity)") == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/arthur/projects/AutoMana && pytest tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py::test_search_multi_color_adds_condition_per_color -v
```

Expected: `FAILED` — `search()` does not accept `colors`

- [ ] **Step 3: Update `query_deps.py`**

`List` is already imported from `typing`. In `src/automana/api/dependancies/query_deps.py`, change line 93:

```python
# before
color: Optional[str] = Query(None, description="Filter by card color"),
# after
colors: Optional[List[str]] = Query(None, alias="color", description="Filter by card color (repeatable: ?color=Blue&color=Green)"),
```

Update the return dict (line ~120):

```python
# before
"color": color,
# after
"colors": colors,
```

- [ ] **Step 4: Update `card_repository.py` — signature + filter loop**

Change the `search()` signature parameter (around line 297):

```python
# before
color: Optional[str] = None,
# after
colors: Optional[list[str]] = None,
```

Replace the single color condition block (around lines 353–360):

```python
# before
if color:
    conditions.append(f"${counter} = ANY(v.color_identity)")
    rf_conditions.append(f"${rf_counter} = ANY(v.color_identity)")
    values.append(color)
    rf_values.append(color)
    counter += 1
    rf_counter += 1

# after
for c in (colors or []):
    conditions.append(f"${counter} = ANY(v.color_identity)")
    rf_conditions.append(f"${rf_counter} = ANY(v.color_identity)")
    values.append(c)
    rf_values.append(c)
    counter += 1
    rf_counter += 1
```

- [ ] **Step 5: Run all card repo tests**

```bash
cd /home/arthur/projects/AutoMana && pytest tests/unit/core/repositories/card_catalog/ -v
```

Expected: all `PASSED`

- [ ] **Step 6: Commit**

```bash
git add src/automana/api/dependancies/query_deps.py src/automana/core/repositories/card_catalog/card_repository.py tests/unit/core/repositories/card_catalog/test_card_repository_search_promo.py
git commit -m "feat(backend): expand color filter to multi-value colors[]"
```

---

## Task 4: Frontend — types.ts + api.ts

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts`
- Modify: `src/frontend/src/features/cards/api.ts`
- Test: `src/frontend/src/features/cards/__tests__/api.test.ts` (add test)

- [ ] **Step 1: Update `types.ts`**

```typescript
// CardGroupBy: narrow to rarity only
export type CardGroupBy = 'rarity'

// CardSearchParams: add sort_by, sort_order, colors, card_type
export interface CardSearchParams {
  q?: string
  set?: string
  artist?: string
  unique_card_id?: string
  rarity?: string
  finish?: string
  layout?: string
  minPrice?: number
  maxPrice?: number
  promoTypes?: string[]
  group?: CardGroupBy
  sort_by?: 'card_name' | 'released_at' | 'price'
  sort_order?: 'asc' | 'desc'
  colors?: string[]
  card_type?: string
}

// CardSummary: add released_at
export interface CardSummary {
  card_version_id: string
  unique_card_id?: string
  card_name: string
  set_code: string
  set_name: string
  finish: 'non-foil' | 'foil' | 'etched'
  rarity_name: 'common' | 'uncommon' | 'rare' | 'mythic'
  price?: number
  price_change_1d: number
  price_change_7d: number
  price_change_30d: number
  image_uri: string | null
  image_normal?: string | null
  spark: number[]
  version_count?: number
  promo_types?: string[]
  collector_number?: string
  released_at?: string | null   // ← add this
}
```

- [ ] **Step 2: Update `api.ts` to forward new params**

In `cardInfiniteSearchQueryOptions`, update the query string builder to include the new params. Replace the existing `qs` building block in `queryFn`:

```typescript
export function cardInfiniteSearchQueryOptions(params: Omit<CardSearchParams, 'page'>) {
  const { group: _group, ...apiParams } = params
  return infiniteQueryOptions({
    queryKey: ['cards', 'search', apiParams],
    queryFn: async ({ pageParam = 0 }) => {
      const token = useAuthStore.getState().token
      const qs = new URLSearchParams()
      if (params.q)              qs.set('q', params.q)
      if (params.set)            qs.set('set', params.set)
      if (params.artist)         qs.set('artist', params.artist)
      if (params.unique_card_id) qs.set('unique_card_id', params.unique_card_id)
      if (params.rarity)         qs.set('rarity', params.rarity)
      if (params.finish)         qs.set('finish', params.finish)
      if (params.layout)         qs.set('layout', params.layout)
      if (params.minPrice != null) qs.set('min_price', String(params.minPrice))
      if (params.maxPrice != null) qs.set('max_price', String(params.maxPrice))
      params.promoTypes?.forEach(pt => qs.append('promo_type', pt))
      if (params.sort_by)        qs.set('sort_by', params.sort_by)
      if (params.sort_order)     qs.set('sort_order', params.sort_order)
      params.colors?.forEach(c => qs.append('color', c))
      if (params.card_type)      qs.set('card_type', params.card_type)
      qs.set('collapse', 'true')
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
        facets: (body.facets as { promo_types?: string[]; rarities?: string[] } | null) ?? null,
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

- [ ] **Step 3: Write API test for new params**

Open `src/frontend/src/features/cards/__tests__/api.test.ts` and add:

```typescript
it('appends sort_by and sort_order to query string', async () => {
  // Use the existing MSW or fetch-mock pattern in this file
  const opts = cardInfiniteSearchQueryOptions({ sort_by: 'price', sort_order: 'asc' })
  // opts.queryKey should include the params
  expect(opts.queryKey).toContain('cards')
  // Check that apiParams has sort fields (group is stripped, sort is kept)
  const [, , apiParams] = opts.queryKey as [string, string, Record<string, unknown>]
  expect(apiParams.sort_by).toBe('price')
  expect(apiParams.sort_order).toBe('asc')
})

it('appends each color as a separate color param', async () => {
  const opts = cardInfiniteSearchQueryOptions({ colors: ['Blue', 'Green'] })
  const [, , apiParams] = opts.queryKey as [string, string, Record<string, unknown>]
  expect(apiParams.colors).toEqual(['Blue', 'Green'])
})
```

- [ ] **Step 4: Run frontend tests**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- --reporter=verbose 2>&1 | grep -E "PASS|FAIL|api\.test"
```

Expected: api tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/cards/types.ts src/frontend/src/features/cards/api.ts src/frontend/src/features/cards/__tests__/api.test.ts
git commit -m "feat(frontend): add sort_by, sort_order, colors, card_type, released_at to card search types"
```

---

## Task 5: Frontend — SearchFilters: Sort + Group By simplification

**Files:**
- Modify: `src/frontend/src/features/cards/components/SearchFilters.tsx`
- Modify: `src/frontend/src/features/cards/components/SearchFilters.module.css`
- Test: `src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx`

- [ ] **Step 1: Write failing tests**

Add to `src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx`:

```typescript
it('renders sort section with Name A→Z button', () => {
  render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
  expect(screen.getByRole('button', { name: /name a→z/i })).toBeTruthy()
})

it('renders sort section with Newest and Cheapest buttons', () => {
  render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
  expect(screen.getByRole('button', { name: /newest/i })).toBeTruthy()
  expect(screen.getByRole('button', { name: /cheapest/i })).toBeTruthy()
})

it('does not render Set or Finish as group-by options', () => {
  render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
  // "Set" appears as a filter label but not as a group-by pill button
  const groupSection = screen.getByText(/group by/i).closest('section')!
  expect(groupSection.querySelector('[data-group="set"]')).toBeNull()
  expect(groupSection.querySelector('[data-group="finish"]')).toBeNull()
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- SearchFilters --reporter=verbose 2>&1 | tail -20
```

- [ ] **Step 3: Update `SearchFilters.tsx` — Sort section + simplified Group by**

Replace the top of `SearchFilters.tsx` with the following constants and updated props:

```typescript
// src/frontend/src/features/cards/components/SearchFilters.tsx
import { useNavigate } from '@tanstack/react-router'
import type { CardGroupBy, CardSearchParams } from '../types'
import { SearchBarWithSuggestions } from './SearchBarWithSuggestions'
import styles from './SearchFilters.module.css'

const FINISHES = ['non-foil', 'foil', 'etched'] as const
const LAYOUTS = ['normal', 'token', 'transform', 'saga', 'adventure'] as const

const GROUPINGS: ReadonlyArray<{ value: CardGroupBy | 'none'; label: string }> = [
  { value: 'none',   label: 'None' },
  { value: 'rarity', label: 'Rarity' },
]

type SortOption = { label: string; sort_by: 'card_name' | 'released_at' | 'price'; sort_order: 'asc' | 'desc' }
const SORT_OPTIONS: ReadonlyArray<SortOption> = [
  { label: 'Name A→Z', sort_by: 'card_name',   sort_order: 'asc'  },
  { label: 'Newest',   sort_by: 'released_at', sort_order: 'desc' },
  { label: 'Oldest',   sort_by: 'released_at', sort_order: 'asc'  },
  { label: 'Cheapest', sort_by: 'price',        sort_order: 'asc'  },
  { label: 'Priciest', sort_by: 'price',        sort_order: 'desc' },
]
```

Update the `SearchFiltersProps` interface and component signature:

```typescript
export type PriceTrend = 'rising' | 'stable' | 'falling'

interface SearchFiltersProps {
  params: CardSearchParams
  promoTypeFacets: string[]
  rarityFacets: string[]
  priceTrend: PriceTrend | undefined
  onPriceTrendChange: (v: PriceTrend | undefined) => void
  upcomingOnly: boolean
  onUpcomingOnlyChange: (v: boolean) => void
}

export function SearchFilters({
  params,
  promoTypeFacets,
  rarityFacets,
  priceTrend,
  onPriceTrendChange,
  upcomingOnly,
  onUpcomingOnlyChange,
}: SearchFiltersProps) {
  const navigate = useNavigate({ from: '/search' })

  function update(patch: Partial<CardSearchParams>) {
    navigate({ search: (prev) => ({ ...prev, ...patch }) })
  }
  // ... (rest of existing helpers: togglePromoType, selectedPromoCount)
```

Add the Sort section in the JSX, above the Group by section:

```tsx
{/* SORT */}
<section className={styles.group}>
  <div className={styles.groupLabel}>Sort</div>
  <div className={styles.finishGrid} style={{ gridTemplateColumns: '1fr 1fr' }}>
    {SORT_OPTIONS.map(({ label, sort_by, sort_order }) => {
      const active = (params.sort_by ?? 'card_name') === sort_by &&
                     (params.sort_order ?? 'asc') === sort_order
      return (
        <button
          key={label}
          className={[styles.finishBtn, active ? styles.finishActive : ''].join(' ')}
          onClick={() => update({ sort_by, sort_order })}
        >
          {label}
        </button>
      )
    })}
  </div>
</section>
```

Update Group by section to use simplified `GROUPINGS`:

```tsx
{/* GROUP BY */}
<section className={styles.group}>
  <div className={styles.groupLabel}>Group by</div>
  <div className={styles.finishGrid}>
    {GROUPINGS.map(({ value, label }) => {
      const active = value === 'none' ? !params.group : params.group === value
      return (
        <button
          key={value}
          data-group={value}
          className={[styles.finishBtn, active ? styles.finishActive : ''].join(' ')}
          onClick={() => update({ group: value === 'none' ? undefined : value as CardGroupBy })}
        >
          {label}
        </button>
      )
    })}
  </div>
</section>
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- SearchFilters --reporter=verbose 2>&1 | tail -20
```

Expected: all tests `PASSED`

> **Note:** The existing Rarity, Finish, Layout, and Promo type sections remain unchanged in the JSX. Only the GROUPINGS constant and the new Sort section are modified in this task.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/cards/components/SearchFilters.tsx src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx
git commit -m "feat(frontend): add sort controls and simplify group-by to None/Rarity"
```

---

## Task 6: Frontend — SearchFilters: Color, Type, Price trend, Upcoming

**Files:**
- Modify: `src/frontend/src/features/cards/components/SearchFilters.tsx`
- Modify: `src/frontend/src/features/cards/components/SearchFilters.module.css`
- Test: `src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx`

- [ ] **Step 1: Write failing tests**

Add to `SearchFilters.promo.test.tsx`:

```typescript
it('renders Color section with W U B R G C Multi pills', () => {
  render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
  expect(screen.getByRole('button', { name: 'W' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'U' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Multi' })).toBeTruthy()
})

it('toggles a color on click — adds to colors array', () => {
  navigateMock.mockClear()
  render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
  fireEvent.click(screen.getByRole('button', { name: 'U' }))
  expect(navigateMock).toHaveBeenCalledOnce()
})

it('renders Price trend section with Rising Stable Falling', () => {
  render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={vi.fn()} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
  expect(screen.getByText(/rising/i)).toBeTruthy()
  expect(screen.getByText(/falling/i)).toBeTruthy()
})

it('calls onPriceTrendChange when Rising is clicked', () => {
  const onChange = vi.fn()
  render(<SearchFilters params={BASE_PARAMS} promoTypeFacets={[]} rarityFacets={[]} priceTrend={undefined} onPriceTrendChange={onChange} upcomingOnly={false} onUpcomingOnlyChange={vi.fn()} />, { wrapper: Wrapper })
  fireEvent.click(screen.getByText(/↑ rising/i))
  expect(onChange).toHaveBeenCalledWith('rising')
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- SearchFilters --reporter=verbose 2>&1 | tail -20
```

- [ ] **Step 3: Add Color, Type, Price trend, Upcoming sections to `SearchFilters.tsx`**

Add these constants at the top of the file:

```typescript
type ColorCode = 'White' | 'Blue' | 'Black' | 'Red' | 'Green' | 'Colorless' | 'Multi'
const COLOR_OPTIONS: ReadonlyArray<{ label: string; value: ColorCode | 'Multi' }> = [
  { label: 'W', value: 'White' },
  { label: 'U', value: 'Blue' },
  { label: 'B', value: 'Black' },
  { label: 'R', value: 'Red' },
  { label: 'G', value: 'Green' },
  { label: 'C', value: 'Colorless' },
  { label: 'Multi', value: 'Multi' },
]

const CARD_TYPES = ['Creature', 'Instant', 'Sorcery', 'Enchantment', 'Artifact', 'Land', 'Planeswalker'] as const
```

Add a `toggleColor` helper inside the component:

```typescript
function toggleColor(value: string) {
  const current = params.colors ?? []
  const next = current.includes(value) ? current.filter((c) => c !== value) : [...current, value]
  update({ colors: next.length > 0 ? next : undefined })
}
```

Add the Color section in the JSX (after Group by):

```tsx
{/* COLOR */}
<section className={styles.group}>
  <div className={styles.groupLabel}>Color</div>
  <div className={styles.colorGrid}>
    {COLOR_OPTIONS.map(({ label, value }) => {
      const active = params.colors?.includes(value) ?? false
      return (
        <button
          key={value}
          aria-label={value}
          title={value}
          className={[
            styles.colorBtn,
            styles[`color${value}`],
            active ? styles.colorActive : '',
          ].filter(Boolean).join(' ')}
          onClick={() => toggleColor(value)}
        >
          {label}
        </button>
      )
    })}
  </div>
</section>

{/* TYPE */}
<section className={styles.group}>
  <div className={styles.groupLabel}>Type</div>
  <div className={styles.finishGrid} style={{ gridTemplateColumns: '1fr 1fr' }}>
    {CARD_TYPES.map((t) => (
      <button
        key={t}
        className={[styles.finishBtn, params.card_type === t ? styles.finishActive : ''].join(' ')}
        onClick={() => update({ card_type: params.card_type === t ? undefined : t })}
      >
        {t}
      </button>
    ))}
  </div>
</section>

{/* PRICE TREND */}
<section className={styles.group}>
  <div className={styles.groupLabel}>Price trend (7d)</div>
  <div className={styles.finishGrid}>
    {([['rising', '↑ Rising'], ['stable', '→ Stable'], ['falling', '↓ Falling']] as const).map(([val, label]) => (
      <button
        key={val}
        className={[styles.finishBtn, priceTrend === val ? styles.finishActive : ''].join(' ')}
        onClick={() => onPriceTrendChange(priceTrend === val ? undefined : val)}
      >
        {label}
      </button>
    ))}
  </div>
</section>

{/* UPCOMING */}
<section className={styles.group}>
  <div className={styles.groupLabel}>Upcoming</div>
  <label className={styles.checkRow}>
    <input
      type="checkbox"
      checked={upcomingOnly}
      onChange={(e) => onUpcomingOnlyChange(e.target.checked)}
    />
    Show upcoming only
  </label>
</section>
```

- [ ] **Step 4: Add CSS for Color pills to `SearchFilters.module.css`**

Append to the end of `SearchFilters.module.css`:

```css
.colorGrid { display: flex; flex-wrap: wrap; gap: 6px; }
.colorBtn {
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 600;
  border: 1px solid var(--hd-border);
  color: var(--hd-muted);
  background: transparent;
  cursor: pointer;
  transition: border-color 80ms, color 80ms, background 80ms;
}
.colorWhite.colorActive   { border-color: #e8dfc8; color: #e8dfc8; background: rgba(232,223,200,.12); }
.colorBlue.colorActive    { border-color: #5b9bd5; color: #5b9bd5; background: rgba(91,155,213,.12); }
.colorBlack.colorActive   { border-color: #aaa;    color: #aaa;    background: rgba(170,170,170,.10); }
.colorRed.colorActive     { border-color: #d95f5f; color: #d95f5f; background: rgba(217,95,95,.12); }
.colorGreen.colorActive   { border-color: #4caf50; color: #4caf50; background: rgba(76,175,80,.12); }
.colorColorless.colorActive { border-color: #888; color: #888; background: rgba(136,136,136,.10); }
.colorMulti.colorActive   { border-color: #f5c518; color: #f5c518; background: rgba(245,197,24,.12); }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- SearchFilters --reporter=verbose 2>&1 | tail -20
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/cards/components/SearchFilters.tsx src/frontend/src/features/cards/components/SearchFilters.module.css src/frontend/src/features/cards/components/__tests__/SearchFilters.promo.test.tsx
git commit -m "feat(frontend): add Color, Type, Price trend, Upcoming filters to SearchFilters"
```

---

## Task 7: Frontend — SearchResults: price label + simplified buildGroups

**Files:**
- Modify: `src/frontend/src/features/cards/components/SearchResults.tsx`
- Modify: `src/frontend/src/features/cards/components/SearchResults.module.css`

- [ ] **Step 1: Simplify `buildGroups` — remove set and finish branches**

In `SearchResults.tsx`, replace the entire `buildGroups` function and the `FINISH_ORDER` constant:

```typescript
// Remove FINISH_ORDER entirely (no longer needed)

function buildGroups(cards: CardSummary[], groupBy: CardGroupBy | undefined): CardGroup[] {
  if (!groupBy) return [{ key: '__all__', label: '', cards }]

  const buckets = new Map<string, CardGroup>()
  for (const card of cards) {
    const key = card.rarity_name
    const label = card.rarity_name.charAt(0).toUpperCase() + card.rarity_name.slice(1)
    if (!buckets.has(key)) buckets.set(key, { key, label, cards: [] })
    buckets.get(key)!.cards.push(card)
  }

  const groups = Array.from(buckets.values())
  groups.sort((a, b) => (RARITY_ORDER[a.key] ?? 99) - (RARITY_ORDER[b.key] ?? 99))
  return groups
}
```

- [ ] **Step 2: Update the price display in `renderCard`**

In `renderCard`, find the price span (around line 153) and replace it:

```tsx
{(() => {
  const today = new Date().toISOString().slice(0, 10)
  const isUpcoming = card.released_at != null && card.released_at > today
  if (card.price != null) {
    return (
      <span className={[styles.price, delta >= 0 ? styles.up : styles.down].join(' ')}>
        ${card.price.toFixed(2)}
      </span>
    )
  }
  if (isUpcoming) {
    return <span className={`${styles.price} ${styles.unreleased}`}>Not yet released</span>
  }
  return <span className={styles.price}>N/A</span>
})()}
```

Also update the `delta` variable to handle null safely (it may already be 0 for unreleased cards):

```typescript
const delta = card.price_change_1d ?? 0
```

- [ ] **Step 3: Add `.unreleased` class to `SearchResults.module.css`**

Append to `SearchResults.module.css`:

```css
.unreleased { color: #b8860b; font-style: italic; font-weight: 400; }
```

- [ ] **Step 4: Run frontend tests**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- --reporter=verbose 2>&1 | grep -E "PASS|FAIL|SearchResults"
```

Expected: no regressions

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/cards/components/SearchResults.tsx src/frontend/src/features/cards/components/SearchResults.module.css
git commit -m "feat(frontend): show 'Not yet released' for upcoming cards; simplify buildGroups to rarity only"
```

---

## Task 8: Frontend — SetCard upcoming badge

**Files:**
- Modify: `src/frontend/src/features/cards/components/SetCard.tsx`
- Modify: `src/frontend/src/features/cards/components/SetCard.module.css`
- Test: `src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx`

- [ ] **Step 1: Write failing test**

Add to `SetCard.test.tsx`:

```typescript
it('shows UPCOMING badge when released_at is in the future', () => {
  const futureSet: SetBrowseItem = {
    ...mockSet,
    released_at: '2099-01-01',
  }
  render(<SetCard set={futureSet} onSelect={vi.fn()} />)
  expect(screen.getByText('UPCOMING')).toBeTruthy()
})

it('does not show UPCOMING badge for past sets', () => {
  render(<SetCard set={mockSet} onSelect={vi.fn()} />)
  expect(screen.queryByText('UPCOMING')).toBeNull()
})

it('applies upcoming class when released_at is in the future', () => {
  const futureSet: SetBrowseItem = { ...mockSet, released_at: '2099-01-01' }
  const { container } = render(<SetCard set={futureSet} onSelect={vi.fn()} />)
  expect(container.querySelector('button')!.className).toMatch(/upcoming/)
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- SetCard --reporter=verbose 2>&1 | tail -20
```

- [ ] **Step 3: Update `SetCard.tsx`**

Full updated `SetCard.tsx`:

```typescript
import type { SetBrowseItem } from '../types'
import { formatMonth } from '../utils/formatMonth'
import styles from './SetCard.module.css'

function iconUrl(set: SetBrowseItem): string {
  return set.icon_svg_uri || `https://svgs.scryfall.io/sets/${set.set_code.toLowerCase()}.svg`
}

function prettyType(t: string): string {
  const labels: Record<string, string> = {
    expansion: 'Expansion', core: 'Core', masters: 'Masters',
    commander: 'Commander', draft_innovation: 'Draft Innovation',
    alchemy: 'Alchemy', funny: 'Funny', promo: 'Promo',
    starter: 'Starter', duel_deck: 'Duel Deck',
    from_the_vault: 'From the Vault', premium_deck: 'Premium Deck',
    spellbook: 'Spellbook', archenemy: 'Archenemy',
    planechase: 'Planechase', vanguard: 'Vanguard',
    treasure_chest: 'Treasure Chest', box: 'Box Set',
    token: 'Token', memorabilia: 'Memorabilia',
    jumpstart: 'Jumpstart', minigame: 'Minigame',
  }
  return labels[t] ?? t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

interface SetCardProps {
  set: SetBrowseItem
  isChild?: boolean
  onSelect: (code: string) => void
}

export function SetCard({ set, isChild = false, onSelect }: SetCardProps) {
  const today = new Date().toISOString().slice(0, 10)
  const isUpcoming = set.released_at != null && set.released_at > today

  return (
    <button
      className={[
        styles.card,
        isChild ? styles.childCard : '',
        isUpcoming ? styles.upcoming : '',
      ].filter(Boolean).join(' ')}
      onClick={() => onSelect(set.set_code)}
      type="button"
      title={set.set_name}
    >
      <div className={styles.art}>
        <div className={[styles.artInner, isUpcoming ? styles.artUpcoming : ''].filter(Boolean).join(' ')}>
          {set.key_art_uri && (
            <div
              className={styles.bgArt}
              style={{ backgroundImage: `url("${set.key_art_uri}")` }}
            />
          )}
          <div
            className={styles.iconMask}
            style={{ maskImage: `url("${iconUrl(set)}")`, WebkitMaskImage: `url("${iconUrl(set)}")` }}
            aria-hidden
          />
          {isUpcoming && (
            <span className={styles.upcomingBadge} aria-label="Upcoming set">UPCOMING</span>
          )}
        </div>
      </div>

      <div className={styles.info}>
        <div className={styles.codeRow}>
          <span className={styles.nameCode}>{set.set_name} — {set.set_code.toUpperCase()}</span>
          <span className={[styles.date, isUpcoming ? styles.dateUpcoming : ''].filter(Boolean).join(' ')}>
            {formatMonth(set.released_at)}
          </span>
        </div>
        <div className={styles.meta}>
          <span className={styles.type}>{prettyType(set.set_type)}</span>
          <span className={styles.count}>{set.card_count}</span>
        </div>
      </div>
    </button>
  )
}
```

- [ ] **Step 4: Add upcoming styles to `SetCard.module.css`**

Append to `SetCard.module.css`:

```css
/* Upcoming set treatment */
.upcoming {
  outline: 1px solid #b8860b;
  border-radius: 6px;
}
.artUpcoming {
  background: linear-gradient(160deg, #2a2200 0%, rgba(184,134,11,0.15) 100%);
}
.upcomingBadge {
  position: absolute;
  top: 6px;
  right: 6px;
  background: #b8860b;
  color: #000;
  font-size: 9px;
  font-family: var(--font-mono);
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  letter-spacing: 0.5px;
  z-index: 3;
  pointer-events: none;
}
.dateUpcoming { color: #b8860b; }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- SetCard --reporter=verbose 2>&1 | tail -20
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/cards/components/SetCard.tsx src/frontend/src/features/cards/components/SetCard.module.css src/frontend/src/features/cards/components/__tests__/SetCard.test.tsx
git commit -m "feat(frontend): upcoming badge + gold border for future sets in SetCard"
```

---

## Task 9: Frontend — search.tsx: zod schema + state threading

**Files:**
- Modify: `src/frontend/src/routes/search.tsx`

Wire `priceTrend` and `upcomingOnly` local state, update the zod schema to narrow `group`, and apply client-side filters before passing `cards` to `SearchResults`.

- [ ] **Step 1: Update `search.tsx`**

Full updated `search.tsx`:

```typescript
// src/frontend/src/routes/search.tsx
import { useState, useMemo } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { z } from 'zod'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { SearchFilters, type PriceTrend } from '../features/cards/components/SearchFilters'
import { SearchResults } from '../features/cards/components/SearchResults'
import { SetBrowser } from '../features/cards/components/SetBrowser'
import { SelectedSetBanner } from '../features/cards/components/SelectedSetBanner'
import { cardInfiniteSearchQueryOptions, setBrowseQueryOptions } from '../features/cards/api'
import styles from './Search.module.css'

const searchSchema = z.object({
  q:              z.string().optional(),
  set:            z.string().optional(),
  artist:         z.string().optional(),
  unique_card_id: z.string().uuid().optional(),
  rarity:         z.string().optional(),
  finish:         z.string().optional(),
  layout:         z.string().optional().default('normal'),
  minPrice:       z.number().optional(),
  maxPrice:       z.number().optional(),
  promoTypes:     z.array(z.string()).optional(),
  group:          z.enum(['rarity']).optional(),
  sort_by:        z.enum(['card_name', 'released_at', 'price']).optional(),
  sort_order:     z.enum(['asc', 'desc']).optional(),
  colors:         z.array(z.string()).optional(),
  card_type:      z.string().optional(),
})

export const Route = createFileRoute('/search')({
  validateSearch: searchSchema,
  component: SearchPage,
})

type Mode = 'set' | 'card'

function SearchPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: '/search' })

  useQuery(setBrowseQueryOptions())

  const [mode, setMode] = useState<Mode>('card')
  const [priceTrend, setPriceTrend] = useState<PriceTrend | undefined>(undefined)
  const [upcomingOnly, setUpcomingOnly] = useState(false)

  const shouldFetchCards = !!search.set || !!search.unique_card_id || mode === 'card'

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    ...cardInfiniteSearchQueryOptions(search),
    enabled: shouldFetchCards,
  })

  const rawCards = data?.pages?.flatMap(p => p.cards) ?? []
  const total = data?.pages?.[0]?.pagination?.total_count ?? 0
  const promoTypeFacets = data?.pages?.[0]?.facets?.promo_types ?? []
  const rarityFacets = data?.pages?.[0]?.facets?.rarities ?? []

  // Client-side filters applied after fetch
  const cards = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10)
    let result = rawCards
    if (upcomingOnly) result = result.filter(c => c.released_at != null && c.released_at > today)
    if (priceTrend === 'rising')  result = result.filter(c => (c.price_change_7d ?? 0) > 0.05)
    if (priceTrend === 'stable')  result = result.filter(c => (c.price_change_7d ?? 0) >= -0.05 && (c.price_change_7d ?? 0) <= 0.05)
    if (priceTrend === 'falling') result = result.filter(c => (c.price_change_7d ?? 0) < -0.05)
    return result
  }, [rawCards, upcomingOnly, priceTrend])

  const subtitle = search.set
    ? search.set.toUpperCase()
    : search.unique_card_id
      ? cards[0]?.card_name
        ? `all versions of "${cards[0].card_name}"`
        : 'all versions'
      : search.q
        ? `results for "${search.q}"`
        : mode === 'card'
          ? 'search by card name'
          : 'browse by set'

  const filterProps = {
    params: search,
    promoTypeFacets,
    rarityFacets,
    priceTrend,
    onPriceTrendChange: setPriceTrend,
    upcomingOnly,
    onUpcomingOnlyChange: setUpcomingOnly,
  }

  const resultsProps = {
    cards,
    total,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    groupBy: search.group,
  }

  if (search.set) {
    return (
      <AppShell active="search">
        <TopBar title="Search" subtitle={subtitle} />
        <SelectedSetBanner
          setCode={search.set}
          onClear={() => navigate({ search: prev => ({ ...prev, set: undefined }) })}
        />
        <div className={styles.layout}>
          <SearchFilters {...filterProps} />
          <SearchResults {...resultsProps} />
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell active="search">
      <TopBar title="Search" subtitle={subtitle} />

      <div className={styles.tabs} role="tablist" aria-label="Search mode">
        <button
          role="tab"
          aria-selected={mode === 'set'}
          className={`${styles.tab} ${mode === 'set' ? styles.tabActive : ''}`}
          onClick={() => setMode('set')}
        >
          {mode === 'set' && <span className={styles.tabDot} aria-hidden />}
          By Set
        </button>
        <button
          role="tab"
          aria-selected={mode === 'card'}
          className={`${styles.tab} ${mode === 'card' ? styles.tabActive : ''}`}
          onClick={() => setMode('card')}
        >
          {mode === 'card' && <span className={styles.tabDot} aria-hidden />}
          By Card Name
        </button>
      </div>

      {mode === 'set' ? (
        <SetBrowser
          onSelect={(code) => navigate({ search: prev => ({ ...prev, set: code }) })}
        />
      ) : (
        <div className={styles.layout}>
          <SearchFilters {...filterProps} />
          <SearchResults {...resultsProps} />
        </div>
      )}
    </AppShell>
  )
}
```

- [ ] **Step 2: Run all frontend tests**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- --reporter=verbose 2>&1 | tail -30
```

Expected: all tests `PASSED`

- [ ] **Step 3: Run all backend tests**

```bash
cd /home/arthur/projects/AutoMana && pytest tests/unit/ -v 2>&1 | tail -20
```

Expected: all tests `PASSED`

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/routes/search.tsx
git commit -m "feat(frontend): wire sort, color, type, price-trend, upcoming state into search page"
```

---

## Done

At this point all tasks are complete. Verify the full feature end-to-end by:
1. Starting the dev stack: `dcdev-automana up -d`
2. Opening `http://localhost:3000/search`
3. Checking: Sort buttons appear above Group by; Group by shows only None/Rarity; Color pills render; an upcoming set has the gold border + UPCOMING badge in the Set Browser; a known upcoming card shows "Not yet released" instead of N/A
