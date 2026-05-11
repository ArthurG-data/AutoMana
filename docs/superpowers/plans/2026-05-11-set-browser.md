# Set Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a set browser to `/search` — compact row list of all non-digital sets (newest first) that replaces the card grid when no set is selected; clicking a row collapses it into a sticky banner and shows filtered cards below.

**Architecture:** URL-state-driven: the `set` param (already in the route schema) controls mode. Pre-fetching the browse list in `SearchPage` means `SelectedSetBanner` always has its data even on direct deep-links. Backend adds one `browse()` repo method, one service, one endpoint; card search gains an exact `set_code` filter to replace the currently-ignored `?set=` param.

**Tech Stack:** Python/FastAPI (asyncpg), Pydantic v2, React 18 + TanStack Query v5 + TanStack Router, CSS Modules.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/automana/core/models/card_catalog/set.py` | Add `SetBrowseItem` model |
| Modify | `src/automana/core/repositories/card_catalog/set_repository.py` | Add `browse()` method |
| Modify | `src/automana/core/services/card_catalog/set_service.py` | Register `card_catalog.set.browse` service |
| Modify | `src/automana/api/routers/mtg/set_reference.py` | Add `GET /browse` endpoint |
| Modify | `src/automana/api/dependancies/query_deps.py` | Add `set_code` (alias `set`) to `card_search_params` |
| Modify | `src/automana/core/repositories/card_catalog/card_repository.py` | Add exact `set_code` filter to `search()` |
| Modify | `src/automana/core/services/card_catalog/card_service.py` | Pass `set_code` through to repository |
| Create | `tests/unit/core/test_set_browse.py` | Unit tests for browse service (mocked repo) |
| Create | `tests/integration/api/test_set_browse_endpoint.py` | Integration test for `GET /set-reference/browse` |
| Modify | `src/frontend/src/features/cards/types.ts` | Add `SetBrowseItem` TS type |
| Modify | `src/frontend/src/features/cards/api.ts` | Add `setBrowseQueryOptions()` |
| Create | `src/frontend/src/features/cards/components/SetBrowser.tsx` | Set list + inline filter |
| Create | `src/frontend/src/features/cards/components/SetBrowser.module.css` | Styles |
| Create | `src/frontend/src/features/cards/components/SelectedSetBanner.tsx` | Sticky selected-set bar |
| Create | `src/frontend/src/features/cards/components/SelectedSetBanner.module.css` | Styles |
| Modify | `src/frontend/src/routes/search.tsx` | Wire mode switch + pre-fetch |

---

## Task 1: `SetBrowseItem` model + `set_repository.browse()` method

**Files:**
- Modify: `src/automana/core/models/card_catalog/set.py`
- Modify: `src/automana/core/repositories/card_catalog/set_repository.py`

- [ ] **Step 1: Add `SetBrowseItem` to the set model file**

Open `src/automana/core/models/card_catalog/set.py` and append this class after the existing `SetInDB` class (leave all existing code untouched):

```python
class SetBrowseItem(BaseModel):
    set_id: UUID = Field(title="Set UUID")
    set_name: str = Field(title="Full set name")
    set_code: str = Field(title="Three-to-five letter set code")
    set_type: str = Field(title="Category of set (expansion, masters, …)")
    card_count: int = Field(title="Number of card versions in this set")
    released_at: datetime.date = Field(title="Official release date")
    icon_svg_uri: Optional[str] = Field(default=None, title="Scryfall SVG icon URL")

    class Config:
        from_attributes = True
```

- [ ] **Step 2: Add `browse()` to `SetReferenceRepository`**

Open `src/automana/core/repositories/card_catalog/set_repository.py`.  
Append this method inside the `SetReferenceRepository` class, after the existing `list()` method:

```python
async def browse(self) -> list[dict]:
    query = """
        SELECT
            vsm.set_id,
            vsm.set_name,
            vsm.set_code,
            vsm.set_type,
            vsm.card_count,
            vsm.released_at,
            iqr.icon_query_uri AS icon_svg_uri
        FROM card_catalog.joined_set_materialized vsm
        LEFT JOIN card_catalog.icon_set ics ON ics.set_id = vsm.set_id
        LEFT JOIN card_catalog.icon_query_ref iqr
               ON iqr.icon_query_id = ics.icon_query_id
        WHERE vsm.digital = FALSE
        ORDER BY vsm.released_at DESC
    """
    rows = await self.execute_query(query)
    return [dict(r) for r in rows]
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/models/card_catalog/set.py \
        src/automana/core/repositories/card_catalog/set_repository.py
git commit -m "feat(set): add SetBrowseItem model and browse() repository method"
```

---

## Task 2: `card_catalog.set.browse` service + `GET /set-reference/browse` endpoint

**Files:**
- Modify: `src/automana/core/services/card_catalog/set_service.py`
- Modify: `src/automana/api/routers/mtg/set_reference.py`
- Create: `tests/unit/core/test_set_browse.py`
- Create: `tests/integration/api/test_set_browse_endpoint.py`

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/core/test_set_browse.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
from uuid import uuid4

ROWS = [
    {
        "set_id": uuid4(),
        "set_name": "Murders at Karlov Manor",
        "set_code": "mkm",
        "set_type": "expansion",
        "card_count": 286,
        "released_at": date(2024, 2, 9),
        "icon_svg_uri": "https://svgs.scryfall.io/sets/mkm.svg",
    },
    {
        "set_id": uuid4(),
        "set_name": "Arena Base Set",
        "set_code": "anb",
        "set_type": "alchemy",
        "card_count": 60,
        "released_at": date(2020, 6, 25),
        "icon_svg_uri": None,
    },
]


@pytest.mark.asyncio
async def test_browse_returns_set_browse_items():
    from automana.core.services.card_catalog import set_service
    from automana.core.models.card_catalog.set import SetBrowseItem

    mock_repo = AsyncMock()
    mock_repo.browse.return_value = ROWS

    result = await set_service.browse_sets(set_repository=mock_repo)

    assert len(result) == 2
    assert all(isinstance(item, SetBrowseItem) for item in result)
    assert result[0].set_code == "mkm"
    assert result[1].icon_svg_uri is None


@pytest.mark.asyncio
async def test_browse_propagates_repo_error():
    from automana.core.services.card_catalog import set_service

    mock_repo = AsyncMock()
    mock_repo.browse.side_effect = RuntimeError("db gone")

    with pytest.raises(Exception):
        await set_service.browse_sets(set_repository=mock_repo)
```

- [ ] **Step 2: Run test — expect failure**

```bash
python -m pytest tests/unit/core/test_set_browse.py -v
```

Expected: `ImportError` or `AttributeError` because `browse_sets` does not exist yet.

- [ ] **Step 3: Register the service in `set_service.py`**

Open `src/automana/core/services/card_catalog/set_service.py`.  
Add this import at the top if not already present:
```python
from automana.core.models.card_catalog.set import SetBrowseItem
```

Append after the existing `get_all` function (before `add_set`):

```python
@ServiceRegistry.register(
    "card_catalog.set.browse",
    db_repositories=["set"]
)
async def browse_sets(set_repository: SetReferenceRepository) -> list[SetBrowseItem]:
    rows = await set_repository.browse()
    return [SetBrowseItem.model_validate(row) for row in rows]
```

- [ ] **Step 4: Run test — expect pass**

```bash
python -m pytest tests/unit/core/test_set_browse.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Add `GET /browse` endpoint to `set_reference.py`**

Open `src/automana/api/routers/mtg/set_reference.py`.  
Add this import at the top:
```python
from automana.core.models.card_catalog.set import NewSet, NewSets, UpdatedSet, SetBrowseItem
```

Add this route **before** the existing `GET /{set_id}` route (it must be declared before the dynamic segment or FastAPI will match `browse` as a UUID and 422):

```python
@router.get(
    '/browse',
    summary="List all non-digital sets for browsing",
    description=(
        "Returns all non-digital MTG sets sorted by release date (newest first). "
        "Includes set icon SVG URI, card count, and set type. "
        "Intended for the set-browser UI component."
    ),
    response_model=ApiResponse,
    operation_id="sets_browse",
    responses=_SET_ERRORS,
)
async def browse_sets(service_manager: ServiceManagerDep):
    try:
        result = await service_manager.execute_service("card_catalog.set.browse")
        return ApiResponse(
            success=True,
            data=result,
            message="Sets retrieved successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 6: Write the integration test**

Create `tests/integration/api/test_set_browse_endpoint.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_browse_returns_200_with_expected_shape(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    # Schema check on first item if any sets exist
    if body["data"]:
        item = body["data"][0]
        assert "set_code" in item
        assert "set_name" in item
        assert "set_type" in item
        assert "card_count" in item
        assert "released_at" in item
        # icon_svg_uri is allowed to be null
        assert "icon_svg_uri" in item


@pytest.mark.asyncio
async def test_browse_excludes_digital_sets(client):
    response = await client.get("/api/catalog/mtg/set-reference/browse")
    assert response.status_code == 200
    sets = response.json()["data"]
    # No digital-only sets should appear (MTGO/Arena)
    digital_codes = {"tic", "ana", "anb"}  # known digital-only set codes
    returned_codes = {s["set_code"] for s in sets}
    assert returned_codes.isdisjoint(digital_codes), (
        f"Digital sets found in browse response: {returned_codes & digital_codes}"
    )
```

- [ ] **Step 7: Run unit tests**

```bash
python -m pytest tests/unit/core/test_set_browse.py -v
```

Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add src/automana/core/services/card_catalog/set_service.py \
        src/automana/api/routers/mtg/set_reference.py \
        tests/unit/core/test_set_browse.py \
        tests/integration/api/test_set_browse_endpoint.py
git commit -m "feat(set): add card_catalog.set.browse service and GET /set-reference/browse endpoint"
```

---

## Task 3: Add `set_code` filter to card search

The frontend sends `?set=mkm` but the backend's `card_search_params` has no `set` param — it's silently dropped. This task wires it through all three layers.

**Files:**
- Modify: `src/automana/api/dependancies/query_deps.py`
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py`
- Modify: `src/automana/core/services/card_catalog/card_service.py`

- [ ] **Step 1: Add `set_code` to `card_search_params` in `query_deps.py`**

Open `src/automana/api/dependancies/query_deps.py`.  
In the `card_search_params` function, add this parameter after `set_name`:

```python
    set_code: Optional[str] = Query(None, alias="set", description="Filter by exact set code (e.g. 'mkm')"),
```

Add `set_code` to the returned dict at the bottom of the function:

```python
    return {
        "name": search_name,
        "set_name": set_name,
        "set_code": set_code,      # ← add this line
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

- [ ] **Step 2: Add `set_code` filter to `card_repository.search()`**

Open `src/automana/core/repositories/card_catalog/card_repository.py`.  
Add `set_code: Optional[str] = None` to the `search()` signature (after the existing `set_name` parameter):

```python
    async def search(
            self,
            name: Optional[str] = None,
            color: Optional[str] = None,
            rarity: Optional[str] = None,
            set_name: Optional[str] = None,
            set_code: Optional[str] = None,        # ← add this
            mana_cost: Optional[int] = None,
            ...
```

Add the filter block immediately after the existing `set_name` block (around line 257):

```python
        if set_code:
            conditions.append(f"v.set_code = ${counter}")
            rf_conditions.append(f"v.set_code = ${rf_counter}")
            values.append(set_code)
            rf_values.append(set_code)
            counter += 1
            rf_counter += 1
```

- [ ] **Step 3: Pass `set_code` through `card_service.search_cards()`**

Open `src/automana/core/services/card_catalog/card_service.py`.  
In the `search_cards` function signature, add `set_code: Optional[str] = None` after the existing `set_name` parameter.  
In the cache key dict (the `cache_key_data` or similar dict), add `"set_code": set_code`.  
In both the cached-result early return and the `card_repository.search()` call, pass `set_code=set_code`.

Find the block that calls `card_repository.search(...)` and add the argument:

```python
result = await card_repository.search(
    name=name,
    set_name=set_name,
    set_code=set_code,     # ← add this
    rarity=rarity,
    ...
)
```

Also update the cache key dict that feeds Redis (search for the dict containing `"set_name"` and add `"set_code": set_code` next to it).

- [ ] **Step 4: Smoke-test via curl against the running dev server**

```bash
curl -s "http://localhost:8000/api/catalog/mtg/card-reference/?set=mkm&limit=5" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['data']), 'cards, set_codes:', {c['set_code'] for c in d['data']})"
```

Expected output: 5 cards, all with set_code `mkm`.

- [ ] **Step 5: Commit**

```bash
git add src/automana/api/dependancies/query_deps.py \
        src/automana/core/repositories/card_catalog/card_repository.py \
        src/automana/core/services/card_catalog/card_service.py
git commit -m "feat(search): add exact set_code filter to card search (wires frontend ?set= param)"
```

---

## Task 4: Frontend — `SetBrowseItem` type + `setBrowseQueryOptions`

**Files:**
- Modify: `src/frontend/src/features/cards/types.ts`
- Modify: `src/frontend/src/features/cards/api.ts`

- [ ] **Step 1: Add `SetBrowseItem` to `types.ts`**

Open `src/frontend/src/features/cards/types.ts` and append at the end:

```typescript
export interface SetBrowseItem {
  set_id: string
  set_name: string
  set_code: string
  set_type: string
  card_count: number
  released_at: string        // ISO date string e.g. "2024-02-09"
  icon_svg_uri: string | null
}
```

- [ ] **Step 2: Add `setBrowseQueryOptions` to `api.ts`**

Open `src/frontend/src/features/cards/api.ts`.  
Add `SetBrowseItem` to the import from `./types`:

```typescript
import type { CardDetail, CardSearchParams, CardSearchResponse, CardSuggestParams, CardSuggestResponse, CatalogStats, SetBrowseItem } from './types'
```

Append at the end of the file:

```typescript
export function setBrowseQueryOptions() {
  return queryOptions({
    queryKey: ['sets', 'browse'],
    queryFn: () => apiClient<SetBrowseItem[]>('/catalog/mtg/set-reference/browse'),
    staleTime: 1000 * 60 * 60,     // 1 hour — sets don't change often
    gcTime: 1000 * 60 * 60 * 24,   // 24 hours
  })
}
```

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/features/cards/types.ts \
        src/frontend/src/features/cards/api.ts
git commit -m "feat(frontend): add SetBrowseItem type and setBrowseQueryOptions"
```

---

## Task 5: Frontend — `SetBrowser` component

**Files:**
- Create: `src/frontend/src/features/cards/components/SetBrowser.tsx`
- Create: `src/frontend/src/features/cards/components/SetBrowser.module.css`

- [ ] **Step 1: Create `SetBrowser.module.css`**

Create `src/frontend/src/features/cards/components/SetBrowser.module.css`:

```css
/* SetBrowser.module.css */
.wrap { display: flex; flex-direction: column; padding: 24px 36px; }

.filterInput {
  background: var(--hd-surface-alt);
  border: 1px solid var(--hd-border);
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  color: var(--hd-text);
  outline: none;
  margin-bottom: 16px;
  width: 100%;
  max-width: 420px;
}
.filterInput::placeholder { color: var(--hd-muted); }
.filterInput:focus { border-color: rgba(var(--hd-accent-rgb), 0.5); }

.list { display: flex; flex-direction: column; gap: 5px; }

.row {
  background: var(--hd-surface);
  border: 1px solid var(--hd-border);
  border-radius: 8px;
  padding: 9px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  text-align: left;
  width: 100%;
  transition: border-color 0.15s, background 0.15s;
}
.row:hover {
  border-color: rgba(var(--hd-accent-rgb), 0.4);
  background: rgba(var(--hd-accent-rgb), 0.03);
}

.icon {
  width: 28px; height: 28px; flex-shrink: 0;
  background: rgba(var(--hd-blue-rgb), 0.12);
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.icon img { width: 18px; height: 18px; object-fit: contain; }
.iconFallback { width: 16px; height: 16px; opacity: 0.5; }

.name {
  flex: 1;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--hd-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

.code {
  font-family: var(--font-mono);
  font-size: 9px;
  text-transform: uppercase;
  font-weight: 700;
  background: rgba(var(--hd-blue-rgb), 0.15);
  color: var(--hd-blue);
  padding: 2px 6px;
  border-radius: 4px;
}

.type {
  font-size: 9px;
  font-weight: 600;
  background: rgba(var(--hd-accent-rgb), 0.1);
  color: var(--hd-accent);
  padding: 2px 6px;
  border-radius: 4px;
}

.count {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--hd-muted);
  min-width: 28px;
  text-align: right;
}

.empty { font-size: 13px; color: var(--hd-muted); padding: 16px 0; }
```

- [ ] **Step 2: Create `SetBrowser.tsx`**

Create `src/frontend/src/features/cards/components/SetBrowser.tsx`:

```tsx
// src/frontend/src/features/cards/components/SetBrowser.tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { setBrowseQueryOptions } from '../api'
import type { SetBrowseItem } from '../types'
import styles from './SetBrowser.module.css'

const FALLBACK_ICON = (
  <svg className={styles.iconFallback} viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" fill="none"/>
  </svg>
)

function SetRow({ set, onSelect }: { set: SetBrowseItem; onSelect: (code: string) => void }) {
  return (
    <button className={styles.row} onClick={() => onSelect(set.set_code)}>
      <span className={styles.icon}>
        {set.icon_svg_uri
          ? <img src={set.icon_svg_uri} alt="" aria-hidden />
          : FALLBACK_ICON}
      </span>
      <span className={styles.name}>{set.set_name}</span>
      <span className={styles.meta}>
        <span className={styles.code}>{set.set_code}</span>
        <span className={styles.type}>{set.set_type}</span>
      </span>
      <span className={styles.count}>{set.card_count}</span>
    </button>
  )
}

interface SetBrowserProps {
  onSelect: (setCode: string) => void
}

export function SetBrowser({ onSelect }: SetBrowserProps) {
  const [filter, setFilter] = useState('')
  const { data: sets = [], isError } = useQuery(setBrowseQueryOptions())

  const filtered = filter.trim()
    ? sets.filter(s =>
        s.set_name.toLowerCase().includes(filter.toLowerCase()) ||
        s.set_code.toLowerCase().includes(filter.toLowerCase())
      )
    : sets

  if (isError) {
    return (
      <div className={styles.wrap}>
        <p className={styles.empty}>Failed to load sets. Please refresh.</p>
      </div>
    )
  }

  return (
    <div className={styles.wrap}>
      <input
        className={styles.filterInput}
        placeholder="Filter sets…"
        value={filter}
        onChange={e => setFilter(e.target.value)}
        aria-label="Filter sets by name or code"
      />
      <div className={styles.list}>
        {filtered.length === 0
          ? <p className={styles.empty}>No sets match "{filter}"</p>
          : filtered.map(set => (
              <SetRow key={set.set_code} set={set} onSelect={onSelect} />
            ))
        }
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors related to `SetBrowser.tsx` or `SetBrowser.module.css`.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/components/SetBrowser.tsx \
        src/frontend/src/features/cards/components/SetBrowser.module.css
git commit -m "feat(frontend): add SetBrowser component with inline filter"
```

---

## Task 6: Frontend — `SelectedSetBanner` component

**Files:**
- Create: `src/frontend/src/features/cards/components/SelectedSetBanner.tsx`
- Create: `src/frontend/src/features/cards/components/SelectedSetBanner.module.css`

- [ ] **Step 1: Create `SelectedSetBanner.module.css`**

Create `src/frontend/src/features/cards/components/SelectedSetBanner.module.css`:

```css
/* SelectedSetBanner.module.css */
.banner {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 36px;
  background: linear-gradient(
    to right,
    rgba(var(--hd-accent-rgb), 0.08),
    rgba(var(--hd-blue-rgb), 0.04)
  );
  border-bottom: 1px solid rgba(var(--hd-accent-rgb), 0.2);
}

.icon {
  width: 34px; height: 34px; flex-shrink: 0;
  background: rgba(var(--hd-blue-rgb), 0.14);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.icon img { width: 20px; height: 20px; object-fit: contain; }
.iconFallback { width: 18px; height: 18px; opacity: 0.45; }

.info { flex: 1; min-width: 0; }

.name {
  font-size: 13px;
  font-weight: 700;
  color: var(--hd-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 3px;
}

.code {
  font-family: var(--font-mono);
  font-size: 9px;
  text-transform: uppercase;
  font-weight: 700;
  background: rgba(var(--hd-blue-rgb), 0.15);
  color: var(--hd-blue);
  padding: 2px 6px;
  border-radius: 4px;
}

.type {
  font-size: 9px;
  font-weight: 600;
  background: rgba(var(--hd-accent-rgb), 0.1);
  color: var(--hd-accent);
  padding: 2px 6px;
  border-radius: 4px;
}

.detail {
  font-size: 10px;
  color: var(--hd-muted);
}

.changeBtn {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--hd-accent);
  border: 1px solid rgba(var(--hd-accent-rgb), 0.3);
  border-radius: 6px;
  padding: 5px 12px;
  font-weight: 600;
  background: rgba(var(--hd-accent-rgb), 0.07);
  cursor: pointer;
  flex-shrink: 0;
  white-space: nowrap;
  transition: background 0.15s, border-color 0.15s;
}
.changeBtn:hover {
  background: rgba(var(--hd-accent-rgb), 0.14);
  border-color: rgba(var(--hd-accent-rgb), 0.55);
}
```

- [ ] **Step 2: Create `SelectedSetBanner.tsx`**

Create `src/frontend/src/features/cards/components/SelectedSetBanner.tsx`:

```tsx
// src/frontend/src/features/cards/components/SelectedSetBanner.tsx
import { useQuery } from '@tanstack/react-query'
import { setBrowseQueryOptions } from '../api'
import styles from './SelectedSetBanner.module.css'

const FALLBACK_ICON = (
  <svg className={styles.iconFallback} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
  </svg>
)

interface SelectedSetBannerProps {
  setCode: string
  onClear: () => void
}

export function SelectedSetBanner({ setCode, onClear }: SelectedSetBannerProps) {
  const { data: sets = [] } = useQuery(setBrowseQueryOptions())
  const set = sets.find(s => s.set_code === setCode)

  // Render a minimal skeleton while the browse cache warms (sub-second on repeat visits)
  if (!set) {
    return (
      <div className={styles.banner}>
        <div className={styles.info}>
          <div className={styles.name}>{setCode.toUpperCase()}</div>
        </div>
        <button className={styles.changeBtn} onClick={onClear}>↩ Change set</button>
      </div>
    )
  }

  const year = set.released_at.slice(0, 4)

  return (
    <div className={styles.banner}>
      <span className={styles.icon}>
        {set.icon_svg_uri
          ? <img src={set.icon_svg_uri} alt="" aria-hidden />
          : FALLBACK_ICON}
      </span>
      <div className={styles.info}>
        <div className={styles.name}>{set.set_name}</div>
        <div className={styles.meta}>
          <span className={styles.code}>{set.set_code}</span>
          <span className={styles.type}>{set.set_type}</span>
          <span className={styles.detail}>{set.card_count} cards · {year}</span>
        </div>
      </div>
      <button className={styles.changeBtn} onClick={onClear}>↩ Change set</button>
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/features/cards/components/SelectedSetBanner.tsx \
        src/frontend/src/features/cards/components/SelectedSetBanner.module.css
git commit -m "feat(frontend): add SelectedSetBanner component"
```

---

## Task 7: Frontend — Wire `SetBrowser` and `SelectedSetBanner` into `SearchPage`

**Files:**
- Modify: `src/frontend/src/routes/search.tsx`

- [ ] **Step 1: Replace `search.tsx` with the updated version**

Open `src/frontend/src/routes/search.tsx` and replace the full contents with:

```tsx
// src/frontend/src/routes/search.tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { z } from 'zod'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { SearchFilters } from '../features/cards/components/SearchFilters'
import { SearchResults } from '../features/cards/components/SearchResults'
import { SetBrowser } from '../features/cards/components/SetBrowser'
import { SelectedSetBanner } from '../features/cards/components/SelectedSetBanner'
import { cardInfiniteSearchQueryOptions, setBrowseQueryOptions } from '../features/cards/api'
import styles from './Search.module.css'

const searchSchema = z.object({
  q:          z.string().optional(),
  set:        z.string().optional(),
  rarity:     z.string().optional(),
  finish:     z.string().optional(),
  layout:     z.string().optional().default('normal'),
  minPrice:   z.number().optional(),
  maxPrice:   z.number().optional(),
  promoTypes: z.array(z.string()).optional(),
})

export const Route = createFileRoute('/search')({
  validateSearch: searchSchema,
  component: SearchPage,
})

function SearchPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: '/search' })

  // Always pre-fetch browse data so SelectedSetBanner can resolve metadata
  // even when the user lands directly at /search?set=mkm
  useQuery(setBrowseQueryOptions())

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = useInfiniteQuery(
    cardInfiniteSearchQueryOptions(search)
  )

  const cards = data?.pages?.flatMap(p => p.cards) ?? []
  const total = data?.pages?.[0]?.pagination?.total_count ?? 0
  const promoTypeFacets = data?.pages?.[0]?.facets?.promo_types ?? []
  const rarityFacets = data?.pages?.[0]?.facets?.rarities ?? []

  const subtitle = search.set
    ? search.set.toUpperCase()
    : search.q
      ? `results for "${search.q}"`
      : 'browse by set'

  return (
    <AppShell active="collection">
      <TopBar title="Search" subtitle={subtitle} />

      {!search.set ? (
        <SetBrowser
          onSelect={(code) => navigate({ search: prev => ({ ...prev, set: code }) })}
        />
      ) : (
        <>
          <SelectedSetBanner
            setCode={search.set}
            onClear={() => navigate({ search: prev => ({ ...prev, set: undefined }) })}
          />
          <div className={styles.layout}>
            <SearchFilters
              params={search}
              promoTypeFacets={promoTypeFacets}
              rarityFacets={rarityFacets}
            />
            <SearchResults
              cards={cards}
              total={total}
              fetchNextPage={fetchNextPage}
              hasNextPage={hasNextPage}
              isFetchingNextPage={isFetchingNextPage}
            />
          </div>
        </>
      )}
    </AppShell>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd src/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 3: Start the dev server and manually verify the golden path**

```bash
dcdev-automana up -d
```

Open `http://localhost:5173/search` (or the configured dev port):

1. **No set selected** — you should see the set browser: a filter input and compact rows (icon, name, code badge, type pill, count).
2. **Type "elden"** in the filter — only sets with "elden" in their name should remain.
3. **Click a set row** — the browser should disappear, a banner appears at the top showing the set icon, name, code, type, card count + year, and a "↩ Change set" button. The card grid loads below.
4. **Apply a rarity filter** in the sidebar — card count should update.
5. **Click "↩ Change set"** — back to set browser.
6. **Navigate directly** to `http://localhost:5173/search?set=mkm` — the banner should render immediately (using pre-fetched browse data).

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/routes/search.tsx
git commit -m "feat(frontend): wire SetBrowser and SelectedSetBanner into SearchPage"
```

---

## Self-Review Notes

**Spec coverage check:**

| Spec requirement | Covered in |
|---|---|
| Compact row tiles (icon, name, code, type, count) | Task 5 `SetRow` |
| Flat list newest-first, non-digital | Task 1 `browse()` SQL |
| Icon from `icon_query_ref`, fallback placeholder | Task 5 `SetRow`, Task 6 `SelectedSetBanner` |
| Inline client-side filter | Task 5 `SetBrowser` |
| Selected set banner with "Change set" | Task 6 |
| Pre-fetch browse data always | Task 7 `useQuery(setBrowseQueryOptions())` in `SearchPage` |
| `set_code` wired through card search | Task 3 |
| Unit tests for browse service | Task 2 |
| Integration test for endpoint | Task 2 |
| Error state in set browser | Task 5 (`isError` branch) |
| "No sets match" empty state | Task 5 |
| `layout` default `'normal'` preserved | Task 7 (schema unchanged) |
