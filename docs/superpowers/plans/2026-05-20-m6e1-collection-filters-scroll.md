# M6E1 Collection UI — Filter Pills & Infinite Scroll Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add finish/status filter pills and infinite scroll pagination to the collection page, closing issues #78 and #79.

**Architecture:** Filter pills are pure client-side state in `collection.tsx` applied to already-loaded entries. Infinite scroll uses an Intersection Observer in a new `useInfiniteEntries` hook, backed by `limit`/`offset` query params added to the backend entries endpoint.

**Tech Stack:** React 18, TanStack Query, Vitest + React Testing Library (frontend); FastAPI + asyncpg (backend)

---

## File Map

| File | Role |
|------|------|
| `src/automana/core/repositories/card_catalog/collection_repository.py` | Add `limit`/`offset` to `get_all_entries` |
| `src/automana/core/services/card_catalog/collection_service.py` | Forward `limit`/`offset` through `list_entries` |
| `src/automana/api/routers/mtg/collection.py` | Accept `limit`/`offset` query params on entries endpoint |
| `tests/integration/api/test_collection_entries_pagination.py` | Integration tests for pagination |
| `src/frontend/src/features/collection/api.ts` | Add `fetchEntriesPage(id, limit, offset)` helper |
| `src/frontend/src/features/collection/hooks/useInfiniteEntries.ts` | New hook: paginated accumulation + Intersection Observer |
| `src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts` | Hook unit tests |
| `src/frontend/src/routes/collection.tsx` | Add filter state, filter logic, filter panel JSX, wire hook |
| `src/frontend/src/routes/Collection.module.css` | Filter + sentinel styles |

---

### Task 1: Backend — paginate `get_all_entries`

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/collection_repository.py:178-220`

- [ ] **Step 1: Add `limit` and `offset` params to `get_all_entries`**

Replace the method signature and query tail:

```python
async def get_all_entries(
    self,
    collection_id: UUID,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> List[dict]:
    query = """
        SELECT ci.item_id,
               ci.collection_id,
               ci.unique_card_id AS card_version_id,
               uc.card_name,
               s.set_code,
               cv.collector_number,
               ci.finish_id,
               cf.code AS finish,
               ci.condition,
               ci.purchase_price,
               ci.currency_code,
               ci.purchase_date,
               ci.language_id,
               cvi.image_uris->>'normal'  AS image_normal,
               ps.price                    AS price,
               ps.price_change_1d          AS price_change_1d,
               ci.ebay_item_id,
               CASE
                   WHEN ci.ebay_item_id IS NOT NULL
                        AND eal.item_id IS NOT NULL
                        AND eal.ended_at IS NULL
                   THEN 'listed'
                   ELSE ci.status
               END AS status
        FROM user_collection.collection_items ci
        JOIN user_collection.collections col
            ON col.collection_id = ci.collection_id AND col.user_id = $2
        JOIN card_catalog.card_version cv ON cv.card_version_id = ci.unique_card_id
        JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
        JOIN card_catalog.sets s ON s.set_id = cv.set_id
        JOIN card_catalog.card_finished cf ON cf.finish_id = ci.finish_id
        LEFT JOIN card_catalog.card_version_illustration cvi
            ON cvi.card_version_id = cv.card_version_id
        LEFT JOIN pricing.mv_card_price_spark ps
            ON ps.card_version_id = ci.unique_card_id
        LEFT JOIN app_integration.ebay_active_listings eal
            ON eal.item_id = ci.ebay_item_id
        WHERE ci.collection_id = $1
        ORDER BY ci.purchase_date DESC, ci.item_id
        LIMIT $3 OFFSET $4;
    """
    rows = await self.execute_query(query, (collection_id, user_id, limit, offset))
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Commit**

```bash
git add src/automana/core/repositories/card_catalog/collection_repository.py
git commit -m "feat(collection): add limit/offset pagination to get_all_entries"
```

---

### Task 2: Backend — thread pagination through service and router

**Files:**
- Modify: `src/automana/core/services/card_catalog/collection_service.py:229-240`
- Modify: `src/automana/api/routers/mtg/collection.py:254-267`

- [ ] **Step 1: Update `list_entries` service to accept and forward pagination**

Replace the `list_entries` function:

```python
@ServiceRegistry.register(
    "card_catalog.collection.list_entries",
    db_repositories=["user_collection"]
)
async def list_entries(
    user_collection_repository: CollectionRepository,
    collection_id: UUID,
    user: UserInDB,
    limit: int = 50,
    offset: int = 0,
) -> List[PublicCollectionEntry]:
    col = await user_collection_repository.get(collection_id, user.unique_id)
    if not col:
        raise card_catalog_exceptions.CollectionNotFoundError(
            f"Collection {collection_id} not found"
        )
    rows = await user_collection_repository.get_all_entries(
        collection_id, user.unique_id, limit=limit, offset=offset
    )
    return [PublicCollectionEntry.model_validate(r) for r in rows]
```

- [ ] **Step 2: Update `list_entries` router endpoint**

Replace the `list_entries` router function:

```python
@router.get(
    '/{collection_id}/entries',
    summary="List all entries in a collection",
    description="Returns cards in the specified collection. Supports limit/offset pagination.",
    response_model=ApiResponse,
    operation_id="collection_entries_list",
    responses={
        404: {"description": "Collection not found"},
    },
)
async def list_entries(
    collection_id: UUID,
    current_user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
):
    try:
        result = await service_manager.execute_service(
            "card_catalog.collection.list_entries",
            collection_id=collection_id,
            user=current_user,
            limit=limit,
            offset=offset,
        )
        return ApiResponse(data=result)
    except CollectionNotFoundError:
        raise HTTPException(status_code=404, detail="Collection not found")
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/services/card_catalog/collection_service.py \
        src/automana/api/routers/mtg/collection.py
git commit -m "feat(collection): thread limit/offset through service and router"
```

---

### Task 3: Backend — integration tests for pagination

**Files:**
- Create: `tests/integration/api/test_collection_entries_pagination.py`

- [ ] **Step 1: Write the tests**

```python
import pytest


@pytest.mark.asyncio
async def test_entries_default_limit_returns_at_most_50(client, auth_headers, seeded_collection):
    """Default page size is 50."""
    collection_id = seeded_collection["collection_id"]
    response = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries",
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) <= 50


@pytest.mark.asyncio
async def test_entries_limit_param_is_respected(client, auth_headers, seeded_collection):
    """?limit=5 returns at most 5 entries."""
    collection_id = seeded_collection["collection_id"]
    response = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries?limit=5",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) <= 5


@pytest.mark.asyncio
async def test_entries_offset_advances_page(client, auth_headers, seeded_collection):
    """Page 1 and page 2 return different items."""
    collection_id = seeded_collection["collection_id"]
    r1 = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries?limit=5&offset=0",
        headers=auth_headers,
    )
    r2 = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries?limit=5&offset=5",
        headers=auth_headers,
    )
    ids1 = {e["item_id"] for e in r1.json()["data"]}
    ids2 = {e["item_id"] for e in r2.json()["data"]}
    assert ids1.isdisjoint(ids2), "Pages must not overlap"


@pytest.mark.asyncio
async def test_entries_exhaustion_returns_empty_list(client, auth_headers, seeded_collection):
    """Offset past the last entry returns an empty list, not an error."""
    collection_id = seeded_collection["collection_id"]
    response = await client.get(
        f"/api/catalog/mtg/collection/{collection_id}/entries?limit=5&offset=99999",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"] == []
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/integration/api/test_collection_entries_pagination.py -v
```

Expected: all 4 pass (or skip gracefully if `seeded_collection` fixture doesn't exist yet — integration tests require a running DB).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/api/test_collection_entries_pagination.py
git commit -m "test(collection): integration tests for entries pagination"
```

---

### Task 4: Frontend — `fetchEntriesPage` API helper

**Files:**
- Modify: `src/frontend/src/features/collection/api.ts`

- [ ] **Step 1: Add `fetchEntriesPage` and update `collectionEntriesQueryOptions`**

Add the following to `api.ts` (keep `collectionEntriesQueryOptions` for backward compat — it now fetches page 0 only, used by the backfill dialog and card picker):

```typescript
const PAGE_SIZE = 50

/** Fetch one page of collection entries. Used by useInfiniteEntries. */
export async function fetchEntriesPage(
  collectionId: string,
  offset: number,
  limit = PAGE_SIZE,
): Promise<CollectionEntry[]> {
  return apiClient<CollectionEntry[]>(
    `/catalog/mtg/collection/${collectionId}/entries?limit=${limit}&offset=${offset}`,
  )
}

export { PAGE_SIZE }
```

Also update `collectionEntriesQueryOptions` to use `limit=50&offset=0` explicitly (makes the URL deterministic for the query cache):

```typescript
export function collectionEntriesQueryOptions(collectionId: string) {
  return queryOptions({
    queryKey: ['collection', 'entries', collectionId] as const,
    queryFn: () =>
      apiClient<CollectionEntry[]>(
        `/catalog/mtg/collection/${collectionId}/entries?limit=${PAGE_SIZE}&offset=0`,
      ),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    enabled: Boolean(collectionId),
  })
}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/features/collection/api.ts
git commit -m "feat(collection): add fetchEntriesPage helper for pagination"
```

---

### Task 5: Frontend — `useInfiniteEntries` hook

**Files:**
- Create: `src/frontend/src/features/collection/hooks/useInfiniteEntries.ts`
- Create: `src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts`:

```typescript
import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useInfiniteEntries } from '../useInfiniteEntries'
import * as api from '../../api'
import type { CollectionEntry } from '../../api'

const makeEntry = (id: string): CollectionEntry => ({
  item_id: id,
  card_version_id: 'cv1',
  card_name: 'Ragavan',
  set_code: 'MH2',
  collector_number: '138',
  finish: 'NONFOIL',
  condition: 'NM',
  purchase_price: '28.00',
  purchase_date: '2024-01-01',
  currency_code: 'USD',
  price: 30,
  price_change_1d: 0,
  status: 'purchased',
})

describe('useInfiniteEntries', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('loads first page on mount', async () => {
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue([makeEntry('e1'), makeEntry('e2')])
    const { result } = renderHook(() => useInfiniteEntries('col1'))
    await waitFor(() => expect(result.current.allEntries).toHaveLength(2))
    expect(api.fetchEntriesPage).toHaveBeenCalledWith('col1', 0, expect.any(Number))
  })

  it('sets hasMore=false when page is smaller than limit', async () => {
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue([makeEntry('e1')])
    const { result } = renderHook(() => useInfiniteEntries('col1'))
    await waitFor(() => expect(result.current.hasMore).toBe(false))
  })

  it('sets hasMore=true when page equals limit', async () => {
    const fullPage = Array.from({ length: 50 }, (_, i) => makeEntry(`e${i}`))
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue(fullPage)
    const { result } = renderHook(() => useInfiniteEntries('col1'))
    await waitFor(() => expect(result.current.hasMore).toBe(true))
  })

  it('fetchNextPage appends entries and advances offset', async () => {
    const page1 = Array.from({ length: 50 }, (_, i) => makeEntry(`e${i}`))
    const page2 = [makeEntry('e50'), makeEntry('e51')]
    vi.spyOn(api, 'fetchEntriesPage')
      .mockResolvedValueOnce(page1)
      .mockResolvedValueOnce(page2)

    const { result } = renderHook(() => useInfiniteEntries('col1'))
    await waitFor(() => expect(result.current.allEntries).toHaveLength(50))

    await act(() => result.current.fetchNextPage())
    await waitFor(() => expect(result.current.allEntries).toHaveLength(52))
    expect(api.fetchEntriesPage).toHaveBeenCalledWith('col1', 50, expect.any(Number))
  })

  it('resets when collectionId changes', async () => {
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue([makeEntry('e1')])
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useInfiniteEntries(id),
      { initialProps: { id: 'col1' } },
    )
    await waitFor(() => expect(result.current.allEntries).toHaveLength(1))
    rerender({ id: 'col2' })
    await waitFor(() => expect(result.current.allEntries).toHaveLength(1))
    expect(api.fetchEntriesPage).toHaveBeenCalledWith('col2', 0, expect.any(Number))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts
```

Expected: FAIL — `useInfiniteEntries` not found.

- [ ] **Step 3: Implement the hook**

Create `src/frontend/src/features/collection/hooks/useInfiniteEntries.ts`:

```typescript
import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchEntriesPage, PAGE_SIZE } from '../api'
import type { CollectionEntry } from '../api'

interface UseInfiniteEntriesResult {
  allEntries: CollectionEntry[]
  isFetchingMore: boolean
  hasMore: boolean
  fetchNextPage: () => Promise<void>
  sentinelRef: React.RefObject<HTMLDivElement>
}

export function useInfiniteEntries(collectionId: string | null): UseInfiniteEntriesResult {
  const [allEntries, setAllEntries] = useState<CollectionEntry[]>([])
  const [isFetchingMore, setIsFetchingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const offsetRef = useRef(0)
  const sentinelRef = useRef<HTMLDivElement>(null)

  // Reset and load first page when collectionId changes
  useEffect(() => {
    if (!collectionId) {
      setAllEntries([])
      setHasMore(false)
      return
    }
    offsetRef.current = 0
    setAllEntries([])
    setHasMore(true)
    setIsFetchingMore(true)
    fetchEntriesPage(collectionId, 0).then((page) => {
      setAllEntries(page)
      offsetRef.current = page.length
      setHasMore(page.length === PAGE_SIZE)
      setIsFetchingMore(false)
    })
  }, [collectionId])

  const fetchNextPage = useCallback(async () => {
    if (!collectionId || isFetchingMore || !hasMore) return
    setIsFetchingMore(true)
    const page = await fetchEntriesPage(collectionId, offsetRef.current)
    setAllEntries((prev) => [...prev, ...page])
    offsetRef.current += page.length
    setHasMore(page.length === PAGE_SIZE)
    setIsFetchingMore(false)
  }, [collectionId, isFetchingMore, hasMore])

  // Intersection Observer wires the sentinel to fetchNextPage
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) fetchNextPage()
      },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [fetchNextPage])

  return { allEntries, isFetchingMore, hasMore, fetchNextPage, sentinelRef }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts
```

Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/collection/hooks/useInfiniteEntries.ts \
        src/frontend/src/features/collection/hooks/__tests__/useInfiniteEntries.test.ts
git commit -m "feat(collection): add useInfiniteEntries hook with Intersection Observer"
```

---

### Task 6: Frontend — filter state and logic in `collection.tsx`

**Files:**
- Modify: `src/frontend/src/routes/collection.tsx`

- [ ] **Step 1: Add filter imports and state**

At the top of the file, add `useCallback` to the React import if not present. Then add filter state after existing `useState` declarations (after line 48):

```typescript
const [finishFilter, setFinishFilter] = useState<Set<string>>(new Set())
const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
const [filterPanelOpen, setFilterPanelOpen] = useState(false)
```

- [ ] **Step 2: Replace the entries query with `useInfiniteEntries`**

Remove the existing `useQuery` for entries (lines 56-58) and replace with:

```typescript
import { useInfiniteEntries } from '../features/collection/hooks/useInfiniteEntries'

// replace the useQuery(collectionEntriesQueryOptions(...)) call:
const {
  allEntries: entries,
  isFetchingMore,
  hasMore,
  sentinelRef,
} = useInfiniteEntries(activeCollectionId)
const isLoading = entries.length === 0 && isFetchingMore
```

- [ ] **Step 3: Update the `filtered` useMemo to include filter logic**

Replace the existing `filtered` useMemo (lines 60-68) with:

```typescript
const filtered = useMemo(() => {
  let result = entries
  if (deferredQuery.trim()) {
    const q = deferredQuery.toLowerCase()
    result = result.filter(
      (e) => e.card_name.toLowerCase().includes(q) || e.set_code.toLowerCase().includes(q),
    )
  }
  if (finishFilter.size > 0)
    result = result.filter((e) => finishFilter.has(e.finish))
  if (statusFilter.size > 0)
    result = result.filter((e) => statusFilter.has(e.status))
  return result
}, [entries, deferredQuery, finishFilter, statusFilter])
```

- [ ] **Step 4: Add toggle helpers**

After the `handleSort` function, add:

```typescript
function toggleFinish(value: string) {
  setFinishFilter((prev) => {
    const next = new Set(prev)
    next.has(value) ? next.delete(value) : next.add(value)
    return next
  })
}

function toggleStatus(value: string) {
  setStatusFilter((prev) => {
    const next = new Set(prev)
    next.has(value) ? next.delete(value) : next.add(value)
    return next
  })
}

function clearFilters() {
  setFinishFilter(new Set())
  setStatusFilter(new Set())
}

const hasActiveFilters = finishFilter.size > 0 || statusFilter.size > 0
```

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/routes/collection.tsx
git commit -m "feat(collection): add filter state and logic to collection page"
```

---

### Task 7: Frontend — filter panel JSX + CSS

**Files:**
- Modify: `src/frontend/src/routes/collection.tsx` (JSX only)
- Modify: `src/frontend/src/routes/Collection.module.css`

- [ ] **Step 1: Add CSS classes**

Append to `src/frontend/src/routes/Collection.module.css`:

```css
/* ── Filter panel ────────────────────────────────────────── */
.filterBtn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid var(--hd-border);
  background: var(--hd-surface);
  color: var(--hd-sub);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 120ms ease;
}
.filterBtn:hover,
.filterBtnActive { border-color: var(--hd-accent); color: var(--hd-accent); }

.filterPanel {
  margin-top: 6px;
  padding: 12px 14px;
  background: var(--hd-surface);
  border: 1px solid var(--hd-border);
  border-radius: 8px;
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.filterGroup { display: flex; flex-direction: column; gap: 6px; }
.filterGroupLabel {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--hd-sub);
}
.filterGroupPills { display: flex; gap: 5px; flex-wrap: wrap; }

.filterRow {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
  min-height: 26px;
}

.filterPill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 20px;
  border: 1px solid var(--hd-border);
  background: var(--hd-surface);
  color: var(--hd-sub);
  font-size: 12px;
  cursor: pointer;
  transition: all 120ms ease;
  white-space: nowrap;
}
.filterPill:hover { border-color: var(--hd-accent); color: var(--hd-text); }
.filterPillActive {
  border-color: var(--hd-accent);
  background: rgba(var(--hd-accent-rgb), 0.12);
  color: var(--hd-accent);
}

.filterPillDismiss {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 20px;
  border: 1px solid rgba(var(--hd-accent-rgb), 0.4);
  background: rgba(var(--hd-accent-rgb), 0.1);
  color: var(--hd-accent);
  font-size: 12px;
  cursor: pointer;
}
.filterPillDismiss:hover { background: rgba(var(--hd-accent-rgb), 0.2); }

.clearAll {
  background: none;
  border: none;
  color: var(--hd-sub);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
}
.clearAll:hover { color: var(--hd-text); }

/* ── Infinite scroll sentinel ────────────────────────────── */
.sentinel { height: 1px; }
.loadingMore {
  text-align: center;
  color: var(--hd-sub);
  font-size: 12px;
  padding: 12px 0;
}
```

- [ ] **Step 2: Add filter panel and active pills JSX**

In the toolbar section of `collection.tsx`, add the "Filters" button after the search box and before the sort controls:

```tsx
<button
  className={cn(styles.filterBtn, filterPanelOpen && styles.filterBtnActive)}
  onClick={() => setFilterPanelOpen((o) => !o)}
  aria-expanded={filterPanelOpen}
  aria-label="Toggle filters"
>
  ⊞ Filters{hasActiveFilters ? ` (${finishFilter.size + statusFilter.size})` : ''}
</button>
```

After the toolbar `div`, add the filter panel (visible when `filterPanelOpen`):

```tsx
{filterPanelOpen && (
  <div className={styles.filterPanel}>
    <div className={styles.filterGroup}>
      <div className={styles.filterGroupLabel}>Finish</div>
      <div className={styles.filterGroupPills}>
        {(['NONFOIL', 'FOIL', 'ETCHED'] as const).map((f) => (
          <button
            key={f}
            className={cn(styles.filterPill, finishFilter.has(f) && styles.filterPillActive)}
            onClick={() => toggleFinish(f)}
          >
            {f}
          </button>
        ))}
      </div>
    </div>
    <div className={styles.filterGroup}>
      <div className={styles.filterGroupLabel}>Status</div>
      <div className={styles.filterGroupPills}>
        {(['purchased', 'listed', 'stashed', 'sold'] as const).map((s) => (
          <button
            key={s}
            className={cn(styles.filterPill, statusFilter.has(s) && styles.filterPillActive)}
            onClick={() => toggleStatus(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  </div>
)}
```

After the filter panel, add the active-filter pills row:

```tsx
{hasActiveFilters && (
  <div className={styles.filterRow}>
    {[...finishFilter].map((f) => (
      <button key={f} className={styles.filterPillDismiss} onClick={() => toggleFinish(f)}>
        Finish: {f} ×
      </button>
    ))}
    {[...statusFilter].map((s) => (
      <button key={s} className={styles.filterPillDismiss} onClick={() => toggleStatus(s)}>
        Status: {s} ×
      </button>
    ))}
    <button className={styles.clearAll} onClick={clearFilters}>Clear all</button>
  </div>
)}
```

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/routes/collection.tsx \
        src/frontend/src/routes/Collection.module.css
git commit -m "feat(collection): add filter panel and active filter pills UI"
```

---

### Task 8: Frontend — wire infinite scroll sentinel

**Files:**
- Modify: `src/frontend/src/routes/collection.tsx` (sentinel rendering)

- [ ] **Step 1: Add sentinel and loading indicator below the grid/table**

Replace the existing render block at the bottom of the `CollectionPage` return:

```tsx
{isLoading ? (
  <div className={styles.loading}>Loading…</div>
) : viewMode === 'grid' ? (
  <CollectionGrid entries={sorted} onRemove={handleRemove} />
) : (
  <CollectionTable
    entries={sorted}
    onRemove={handleRemove}
    sortBy={sortBy}
    sortDir={sortDir}
    onSort={handleSort}
    collectionId={activeCollectionId ?? undefined}
  />
)}

{isFetchingMore && <div className={styles.loadingMore}>Loading more…</div>}
{hasMore && !isFetchingMore && <div ref={sentinelRef} className={styles.sentinel} />}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/routes/collection.tsx
git commit -m "feat(collection): wire infinite scroll sentinel to grid"
```

---

### Task 9: Close issues and push

- [ ] **Step 1: Close #78 and #79 with comments**

```bash
gh issue close 78 --repo ArthurG-data/AutoMana \
  --comment "Implemented: finish/status filter pills with panel toggle, dismissible active pills, and clear-all. Client-side filtering composing with existing text search and sort."

gh issue close 79 --repo ArthurG-data/AutoMana \
  --comment "Implemented: true infinite scroll via Intersection Observer in useInfiniteEntries hook. Backend entries endpoint now accepts limit/offset. Initial page 50 cards, next pages auto-fetched when sentinel enters viewport."
```

- [ ] **Step 2: Open PR**

```bash
git push -u origin HEAD
gh pr create --repo ArthurG-data/AutoMana \
  --title "feat(collection): filter pills + infinite scroll (#78 #79)" \
  --body "$(cat <<'EOF'
## Summary
Closes #78 and #79. Adds finish/status filter pills and infinite scroll to the collection page.

## Changes
- Backend: `limit`/`offset` pagination on `GET /collection/{id}/entries`
- New `useInfiniteEntries` hook (Intersection Observer, page accumulation)
- Filter pills: finish (NONFOIL/FOIL/ETCHED) and status (purchased/listed/stashed/sold)
- Filter panel toggle, dismissible active pills, clear-all

## Test plan
- [ ] Filter by FOIL — only foil cards shown
- [ ] Filter by Listed — only listed cards shown
- [ ] Combine finish + status filters
- [ ] Clear all resets grid
- [ ] Text search + active filter combine correctly
- [ ] Scroll to bottom of 50+ card collection triggers next page load
- [ ] Loading indicator visible during page fetch
- [ ] No extra fetches after last page
EOF
)"
```
