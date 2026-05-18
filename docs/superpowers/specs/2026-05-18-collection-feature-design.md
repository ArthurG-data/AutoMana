# Collection Feature — Design Spec

**Date:** 2026-05-18
**Status:** Approved

## Context

The AutoMana backend has a fully-built collection API (`/collection`, `/collection/{id}/entries`) but the frontend `/collection` route is wired entirely to mock data with no real API calls. The grid view is marked TODO. There is no way for a user to add a card from the search page to their collection. This spec covers connecting the existing pieces end-to-end and adding the missing UI.

**Goals:**
- Users can search for cards and add them to a named collection with one hover interaction
- Users can visualize their collection in a card grid (default) or data table (toggle)
- Multiple named collections are supported (create, switch, delete)
- Collection entries show enriched data: card art, current market price, P&L vs purchase price

---

## Architecture

```
Search page (/search)
  └── SearchResults cards
        └── [hover] "+ Add" button
              └── AddToCollectionPopover
                    └── condition pills + finish label (read-only) + collection dropdown
                          └── POST /collection/{id}/entries

Collection page (/collection)
  ├── Collection tabs (one per collection + "+ New")
  ├── Grid / Table toggle
  ├── CollectionGrid  (new — mirrors SearchResults grid)
  │     └── card art, name, finish badge, condition, market price, P&L
  └── CollectionTable (existing — swap mock → real data)

Backend (one enrichment touch)
  └── collection_repository.py get_all_entries
        └── LEFT JOIN card_catalog.card_version_illustration → image_normal
        └── LEFT JOIN pricing.mv_card_price_spark → price, price_change_1d
        └── PublicCollectionEntry model += image_normal, price, price_change_1d
```

---

## Backend Enrichment

### `src/automana/core/repositories/card_catalog/collection_repository.py`

The `get_all_entries` query already JOINs `card_catalog.card_version cv`. Add two LEFT JOINs:

```sql
LEFT JOIN card_catalog.card_version_illustration cvi
  ON cvi.card_version_id = cv.card_version_id
LEFT JOIN pricing.mv_card_price_spark ps
  ON ps.card_version_id = ci.unique_card_id
```

Add to SELECT:
```sql
cvi.image_uris->>'normal'  AS image_normal,
ps.price                    AS price,
ps.price_change_1d          AS price_change_1d
```

`mv_card_price_spark` is keyed by `card_version_id` only (aggregates across finishes, preferring NONFOIL). LEFT JOINs mean cards without art or price still appear.

### `src/automana/core/models/collections/collection.py`

Add to `PublicCollectionEntry`:
```python
image_normal: Optional[str] = None
price: Optional[float] = None
price_change_1d: float = 0.0
```

No new endpoints. No migration required.

---

## Frontend: New Files

| File | Purpose |
|------|---------|
| `src/frontend/src/features/collection/api.ts` | Query options + mutations for all collection endpoints |
| `src/frontend/src/features/collection/components/CollectionGrid.tsx` | Responsive card grid (2→5 cols, matches SearchResults breakpoints) |
| `src/frontend/src/features/collection/components/CollectionGrid.module.css` | Grid styles |
| `src/frontend/src/features/collection/components/AddToCollectionPopover.tsx` | Hover add form: condition pills, finish label, collection dropdown |
| `src/frontend/src/features/collection/components/AddToCollectionPopover.module.css` | Popover styles |

## Frontend: Modified Files

| File | Change |
|------|--------|
| `src/frontend/src/routes/collection.tsx` | Replace MOCK_COLLECTION with real query; add collection tabs; wire grid/table toggle |
| `src/frontend/src/routes/Collection.module.css` | Add tab row styles |
| `src/frontend/src/features/cards/components/SearchResults.tsx` | Add hover "+ Add" button per card; render AddToCollectionPopover |
| `src/frontend/src/features/cards/components/SearchResults.module.css` | Add hover overlay styles |

---

## Key Data Types (TypeScript)

```typescript
interface Collection {
  collection_id: string
  collection_name: string
  description?: string
  is_active: boolean
}

interface CollectionEntry {
  item_id: string
  card_version_id: string
  card_name: string
  set_code: string
  collector_number: string
  finish: 'NONFOIL' | 'FOIL' | 'ETCHED'
  condition: 'NM' | 'LP' | 'MP' | 'HP' | 'DMG' | 'SP'
  purchase_price: number
  purchase_date: string
  currency_code: string
  image_normal?: string
  price?: number
  price_change_1d: number
}
```

---

## Interaction Flows

### Add a card
1. Hover SearchResults card → "+ Add" button appears (bottom-right corner)
2. Click → `AddToCollectionPopover` anchors to the card
3. Condition pills (NM default), finish shown as read-only label (fixed by card version), collection dropdown
4. No collections yet → first submit auto-creates "My Collection" first
5. Submit → `POST /collection/{id}/entries` → success toast → popover closes

### View collection
1. `/collection` loads → `GET /collection` fetches all user collections → tabs render
2. First tab selected → `GET /collection/{id}/entries` → enriched entries with art + price
3. Grid default → `CollectionGrid` renders; toggle switches to `CollectionTable`
4. Metrics strip (total cards, total value, total cost, P&L) computed from live data

### Create collection
- "+ New" tab → inline name input → `POST /collection` → tab added, auto-selected

### Remove a card
- Grid: hover card → "×" button → `DELETE /collection/{id}/entries/{entryId}`
- Table: Actions column remove → same DELETE call

---

## Verification

1. Create test user + get auth token (see `docs/TESTING_API_FLOW.md`)
2. Search `/search` → hover a card → confirm "+ Add" button appears
3. Click → pick NM condition → submit → confirm `GET /collection/{id}/entries` returns the card with `image_normal` populated
4. Navigate to `/collection` → confirm card appears in grid view with art, price, P&L
5. Toggle to table view → same card visible in row format
6. Create a second collection → add a different card → switch tabs → confirm each tab shows correct cards
7. Remove a card from grid view → confirm it disappears
8. Delete test user (cleanup per `TESTING_API_FLOW.md`)
