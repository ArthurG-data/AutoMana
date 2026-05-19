# Design: Backfill Collection from eBay Listings

**Date:** 2026-05-20
**Branch:** feature/collection-backfill-from-listings

---

## Context

eBay active listings and the user collection both reference `card_version_id` from `card_catalog.card_version`, but the two subsystems have never been connected in the UI. A user who lists cards on eBay should be able to import those listings directly into their collection without re-entering card details manually.

Two cases exist:
- **Matched listings** — `ebay_active_listings.card_version_id IS NOT NULL`. Can be auto-added to a collection in bulk after one confirmation.
- **Unmatched listings** — `card_version_id IS NULL` (listing was scraped before the card was resolved). Require a card search step before adding.

---

## Architecture

### Phase 1 — Confirmation Dialog (matched listings)
1. User clicks "Add to Collection" button on the listings page toolbar.
2. The dialog splits the already-loaded listing data (from `useListingsStore`) into matched vs unmatched using the new `cardVersionId` field.
3. User picks a collection from a dropdown and confirms.
4. Frontend calls the existing `addCollectionEntry()` API for each matched listing.
5. Dialog shows success and offers a link to `/listings/match` for unmatched listings.

### Phase 2 — Matching Page (unmatched listings)
1. Navigate to `/listings/match`, receiving the unmatched listings list via TanStack Router `state`.
2. Page shows one listing at a time: eBay title, condition badge, finish badge.
3. User searches for the card using the existing `CardPicker` component.
4. After selecting a card, user confirms condition (pre-filled from listing, adjustable) and clicks "Add to collection & next".
5. Frontend calls `addCollectionEntry()` and advances to next.
6. "Skip" skips without adding. Progress counter shown: "3 of 12".

---

## Backend Changes

### 1. `src/automana/core/models/ebay/listings.py` — `ItemModel`
Add one field alongside the existing `CatalogFinish` / `CatalogCondition`:
```python
CardVersionId: Optional[UUID] = Field(None, alias="cardVersionId")
```

### 2. `src/automana/core/services/app_integration/ebay/listings_read_service.py`
In the enrichment loop (where `CatalogFinish` and `CatalogCondition` are set), also copy `card_version_id` from the metadata dict:
```python
item = item.model_copy(update={
    "CatalogFinish": meta.get("finish_code"),
    "CatalogCondition": meta.get("condition_code"),
    "CardVersionId": meta.get("card_version_id"),   # new
})
```
The existing `GET_LISTING_META_BATCH` SQL already selects `card_version_id`. Listings without a match won't appear in `catalog_meta`, so their `CardVersionId` defaults to `None`.

No changes to `sales_queries.py` or `sales_repository.py`.

---

## Frontend Changes

### 3. `src/frontend/src/features/ebay/api.ts`
- Add `cardVersionId?: string | null` to `RawEbayItem` interface.
- Add `catalogConditionCode?: string | null` and `catalogFinishCode?: string | null` to `RawEbayItem` (to preserve raw codes alongside display labels).
- In `mapToLiveListing()`, pass through:
  ```ts
  cardVersionId: raw.cardVersionId ?? null,
  catalogConditionCode: raw.catalogCondition ?? null,
  catalogFinishCode: raw.catalogFinish ?? null,
  ```

### 4. `src/frontend/src/features/ebay/mockListings.ts` — `EbayLiveListing`
Add three optional fields:
```ts
cardVersionId?: string | null
catalogConditionCode?: string | null   // NM / LP / MP / HP / DMG
catalogFinishCode?: string | null      // NONFOIL / FOIL / ETCHED / SURGE_FOIL / …
```

### 5. `src/frontend/src/features/collection/components/BackfillConfirmDialog.tsx` (new)
Props: `listings: EbayLiveListing[]`, `onClose: () => void`, `onDone: (unmatched: EbayLiveListing[]) => void`

Logic:
- Split `listings` into `matched` (cardVersionId != null) and `unmatched`.
- Show: "N matched · M need card selection"
- Collection dropdown using existing `collectionsQueryOptions()`.
- Confirm → `Promise.allSettled()` over `addCollectionEntry()` calls:
  - `cardVersionId` from listing
  - condition: `catalogConditionCode` mapped to `CollectionEntry['condition']`; exotic finishes (`SURGE_FOIL`, `RIPPLE_FOIL`, `RAINBOW_FOIL`) mapped to `'FOIL'`.
  - finish: `catalogFinishCode` mapped to `'NONFOIL' | 'FOIL' | 'ETCHED'`.
- On success: shows count, offers "Match remaining N" button calling `onDone(unmatched)`.

### 6. `src/frontend/src/routes/listings.tsx`
- Add "Add to Collection" button in the page toolbar (alongside the existing "New listing" button).
- Wire `BackfillConfirmDialog` open/close state.
- On `onDone(unmatched)` → `navigate({ to: '/listings/match', state: { unmatched, collectionId } })`.

### 7. `src/frontend/src/routes/listings_.match.tsx` (new route)
- Reads `unmatched: EbayLiveListing[]` and `collectionId: string` from route `state`.
- State: `index` (current listing), `selectedCard` (CardSummary | null).
- Shows: listing title, condition/finish badges, progress ("3 of 12").
- `CardPicker` for card search/selection (reuses existing component).
- Condition selector (pills: NM/LP/MP/HP/DMG), defaulting to `catalogConditionCode`.
- "Add to collection & next" → `addCollectionEntry(collectionId, selectedCard.card_version_id, condition, finish)` → advance index.
- "Skip" → advance without adding.
- Completion state: summary ("Added X of Y") + "Back to listings" link.

---

## Finish Code Mapping

Collection entries only accept `NONFOIL | FOIL | ETCHED`. Exotic finishes from the catalog are mapped:

| Catalog code    | Collection finish |
|-----------------|-------------------|
| NONFOIL         | NONFOIL           |
| FOIL            | FOIL              |
| ETCHED          | ETCHED            |
| SURGE_FOIL      | FOIL              |
| RIPPLE_FOIL     | FOIL              |
| RAINBOW_FOIL    | FOIL              |

---

## Files Changed Summary

| File | Change |
|------|--------|
| `core/models/ebay/listings.py` | Add `CardVersionId` field to `ItemModel` |
| `services/ebay/listings_read_service.py` | Pass `card_version_id` through enrichment |
| `frontend/features/ebay/api.ts` | Add 3 fields to `RawEbayItem`; pass through in `mapToLiveListing` |
| `frontend/features/ebay/mockListings.ts` | Add 3 fields to `EbayLiveListing` |
| `frontend/features/collection/components/BackfillConfirmDialog.tsx` | New component |
| `frontend/routes/listings.tsx` | Add "Add to Collection" button + dialog wiring |
| `frontend/routes/listings_.match.tsx` | New route (matching page) |

---

## Verification

1. Start the dev stack (`dcdev-automana up`).
2. Navigate to `/listings` — confirm "Add to Collection" button is visible in toolbar.
3. Click it — dialog should appear, showing matched / unmatched counts.
4. Select a collection and confirm — check `/collection` to see new entries.
5. If unmatched listings exist, click "Match remaining" — confirm `/listings/match` loads the queue.
6. Search for a card via CardPicker, adjust condition, click "Add to collection & next" — confirm entry appears in collection and page advances.
7. Skip one listing — confirm index advances without adding.
8. After all processed, confirm completion screen with correct count.
