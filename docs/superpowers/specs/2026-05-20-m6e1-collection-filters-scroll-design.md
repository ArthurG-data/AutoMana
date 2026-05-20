# M6E1 Collection UI — Filter Pills & Infinite Scroll

**Issues:** #78 (filter dropdowns), #79 (infinite scroll)  
**Date:** 2026-05-20  
**Status:** Approved

---

## Overview

Two additions to the existing collection page (`src/frontend/src/routes/collection.tsx`):

1. **Filter pills** — multi-select toggles for Finish and Status, surfaced as dismissible pills beneath the toolbar.
2. **Infinite scroll** — Intersection Observer that auto-fetches the next page when the user reaches the bottom of the grid, backed by new pagination params on the entries endpoint.

---

## #78 — Filter Pills

### What it does

A "Filters" button in the existing toolbar opens an inline panel showing two filter groups: **Finish** (NONFOIL / FOIL / ETCHED) and **Status** (purchased / listed / stashed / sold). Values are toggled as pills. Active filters appear as dismissible pills in a second row between the toolbar and the grid. A "Clear all" link removes all active filters at once.

Filtering is **client-side only** — no backend changes. It operates on the already-loaded `entries` array, chained after the existing text search and before the sort.

### State

```ts
const [finishFilter, setFinishFilter] = useState<Set<string>>(new Set())
const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
const [filterPanelOpen, setFilterPanelOpen] = useState(false)
```

### Filter logic (added to existing `filtered` useMemo)

```ts
const filtered = useMemo(() => {
  let result = entries
  if (deferredQuery.trim()) {
    const q = deferredQuery.toLowerCase()
    result = result.filter(e =>
      e.card_name.toLowerCase().includes(q) || e.set_code.toLowerCase().includes(q)
    )
  }
  if (finishFilter.size > 0)
    result = result.filter(e => finishFilter.has(e.finish))
  if (statusFilter.size > 0)
    result = result.filter(e => statusFilter.has(e.status))
  return result
}, [entries, deferredQuery, finishFilter, statusFilter])
```

### Components

- Filter logic stays in `collection.tsx` — no new files needed.
- The filter panel and pills are inline JSX within the existing toolbar section.
- No new CSS module; extend `Collection.module.css` with `.filterRow`, `.filterPanel`, `.filterPill`, `.filterPillActive`, `.clearAll`.

### Active filter pill display

Active pills render in a `div.filterRow` between toolbar and metrics strip. Each pill shows `<dim>: <value> ×`. Clicking × removes that value from the set. "Clear all" resets both sets.

### No URL persistence

Filter state lives in React local state. A page refresh resets filters — acceptable for this collection size and usage pattern.

---

## #79 — Infinite Scroll

### Backend change

Add optional `limit` (default 50, max 200) and `offset` (default 0) query params to:

```
GET /collection/{collection_id}/entries
```

**Router** (`collection.py`): accept `limit: int = Query(50, le=200)` and `offset: int = Query(0, ge=0)`, pass to service.

**Service** (`list_entries` in `collection_service.py`): forward to repository.

**Repository** (`get_all_entries` in `collection_repository.py`): append `LIMIT $3 OFFSET $4` to the existing query.

The response shape is unchanged (`ApiResponse` with a list). No total count needed — the frontend detects exhaustion when the returned page is smaller than `limit`.

### Frontend

**Query options** (`collection/api.ts`): `collectionEntriesQueryOptions` becomes a paginated query. Initial call uses `offset=0`. Subsequent pages use `offset = loadedCount`.

**Infinite scroll hook** (`useInfiniteEntries`): a small custom hook in `src/frontend/src/features/collection/hooks/useInfiniteEntries.ts` that manages:
- `allEntries: CollectionEntry[]` — accumulated pages
- `isFetchingMore: boolean`
- `hasMore: boolean` — false when last page returned fewer than `limit` items
- `fetchNextPage()` — appends next page to `allEntries`

**Sentinel** (`CollectionGrid.tsx` / `collection.tsx`): a `<div ref={sentinelRef}>` rendered after the last card. An `IntersectionObserver` calls `fetchNextPage()` when the sentinel enters the viewport. The sentinel is hidden (or replaced with a spinner) while fetching; removed entirely when `!hasMore`.

### Interaction with filters

Filters and search operate on `allEntries` (all loaded pages). When the user applies a filter, they see immediate results from whatever is already loaded. If the filtered result is small and more pages exist, the sentinel may remain visible and trigger additional fetches until `hasMore` is false.

### Page size

50 cards per page. Configurable via the `limit` param; default matches the existing router `limit=100` cap reduced to 50 for perceived performance.

---

## Files to create / modify

| File | Change |
|------|--------|
| `src/frontend/src/routes/collection.tsx` | Add filter state, filter logic, filter panel JSX, wire `useInfiniteEntries` |
| `src/frontend/src/routes/Collection.module.css` | Add `.filterRow`, `.filterPanel`, `.filterPill`, `.filterPillActive`, `.clearAll`, `.sentinel`, `.loadingMore` |
| `src/frontend/src/features/collection/api.ts` | Add `limit` / `offset` to `collectionEntriesQueryOptions` |
| `src/frontend/src/features/collection/hooks/useInfiniteEntries.ts` | New hook — manages paginated entry accumulation + Intersection Observer |
| `src/automana/api/routers/mtg/collection.py` | Add `limit` / `offset` query params to `list_entries` endpoint |
| `src/automana/core/services/card_catalog/collection_service.py` | Forward `limit` / `offset` to repository |
| `src/automana/core/repositories/card_catalog/collection_repository.py` | Add `LIMIT` / `OFFSET` to `get_all_entries` query |

---

## Acceptance criteria

### #78
- [ ] "Filters" button toggles an inline panel showing Finish and Status groups
- [ ] Selecting a value adds a dismissible pill to the active filter row
- [ ] Active filters narrow the grid/table in real time
- [ ] Deselecting a pill (or clicking its value again in the panel) removes the filter
- [ ] "Clear all" removes all active filters
- [ ] Filters compose correctly with text search and sort

### #79
- [ ] Initial load fetches first 50 entries
- [ ] Scrolling to the bottom of the grid fetches the next 50
- [ ] A loading indicator is visible during the fetch
- [ ] No more fetches are triggered when all entries are loaded
- [ ] Filters and search work on all loaded entries across pages
