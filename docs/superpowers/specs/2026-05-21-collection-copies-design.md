# Collection Copies — Design Spec

**Date:** 2026-05-21  
**Branch:** new feature branch from `dev`  
**Scope:** Allow a user to own multiple physical copies of the same card (same version, finish, condition) in a collection, each tracked independently with its own purchase price, date, and status.

---

## Problem

The `collection_items` table has a UNIQUE constraint on `(collection_id, unique_card_id, finish_id, condition)`. This means the same printing in the same condition can only appear once per collection. Attempting to add a second copy silently does nothing (`ON CONFLICT DO NOTHING`). Users who own 4x Sol Ring NM cannot represent that reality.

---

## Approach: Frontend-grouped, flat DB rows

Drop the uniqueness constraint. Each INSERT always produces a new row. The `/entries` API continues returning flat rows. The frontend groups them for display. No new endpoints, no schema restructuring.

---

## Database

**Migration `migration_43_drop_collection_items_unique_constraint.sql`**

```sql
-- migration_43: allow multiple copies of the same card per collection
--
-- The unique constraint (collection_id, unique_card_id, finish_id, condition)
-- previously prevented a user from owning more than one physical copy of the
-- same printing in the same condition. Dropping it lets each INSERT create a
-- new independent row, enabling per-copy price/date/status tracking.
--
-- Existing rows are unaffected — they were already unique.

ALTER TABLE user_collection.collection_items
    DROP CONSTRAINT uq_collection_card_finish_condition;
```

No data migration required. Existing rows remain valid.

---

## Backend

### `collection_repository.py`

**`add_entry`**: Remove the `ON CONFLICT (collection_id, unique_card_id, finish_id, condition) DO NOTHING` clause. Change to a plain `INSERT ... RETURNING`. Every call creates a new row and returns it.

**`get_entry_by_key`**: Remove this method. It looked up a single row by `(collection_id, card_version_id, finish_id, condition)` — ambiguous once duplicates are allowed. It was only used as a post-insert fallback; since `add_entry` now always returns the new row, the fallback is unnecessary.

### Models, service, router — no changes

`AddCollectionEntryRequest`, `PublicCollectionEntry`, `CollectionService`, and the router are all unchanged. The `POST /{collection_id}/entries` endpoint continues returning a single `CollectionEntry` (the newly inserted row).

---

## Frontend

### New utility: `groupEntries`

```ts
// src/frontend/src/features/collection/groupEntries.ts
interface EntryGroup {
  key: string                  // `${card_version_id}:${finish}:${condition}`
  representative: CollectionEntry
  copies: CollectionEntry[]
}

function groupEntries(entries: CollectionEntry[]): EntryGroup[]
```

Groups by `(card_version_id, finish, condition)`. Pure function, no side effects. Used by `CollectionGrid`.

### `CollectionGrid` changes

- Renders one tile per **group** instead of per entry.
- `×N` badge: shown only when `copies.length > 1` (hidden for single copies to avoid noise). Positioned top-left of the tile, styled as a pill consistent with the existing condition/finish badges (neutral colour).
- Local `expandedKey: string | null` state on the grid (or per-tile boolean) — clicking the tile body toggles expanded state.
- When expanded: renders a mini-row list beneath the card image. Each row shows:
  - Condition badge
  - Purchase price
  - Status badge (purchased / listed / stashed / sold)
  - Remove `×` button (calls existing `onRemove(copy.item_id)`)
- When collapsed: shows only the representative copy's price (lowest purchase price or most recent — pick one consistently; use most recent by array order since entries are sorted `purchase_date DESC`).

### `AddToCollectionPopover` changes

- New prop: `existingCopies: number` (caller computes this from loaded entries).
- When `existingCopies > 0`: display "You already have **N** — add another?" above the Add button.
- When `existingCopies === 0`: current behaviour unchanged.
- Caller (`SetBrowser` or wherever the popover is mounted) derives `existingCopies` by filtering the loaded entries by `(card_version_id, finish, condition)` and taking the count.

### Mutations & query invalidation — no changes

After a successful add, `invalidateQueries(['collection', 'entries', collectionId])` already triggers a re-fetch. The grid re-renders with the new copy in the group.

---

## Data flow

```
User clicks "Add to Collection"
  → Popover shows existingCopies count (computed from cached entries)
  → User confirms → POST /entries (unchanged)
  → Backend: plain INSERT, new row, returns new CollectionEntry
  → invalidateQueries → re-fetch /entries
  → groupEntries() → tile shows ×(N+1) badge
```

```
User expands grouped tile
  → Local expanded state toggles
  → Mini-row list renders: one row per copy
  → Remove × on a copy → DELETE /entries/{item_id} → re-fetch
  → If group drops to 1 copy, badge hidden; if 0, tile removed
```

---

## What does NOT change

- API response shape (`CollectionEntry`) — no new fields
- Pagination / infinite scroll hooks
- `CollectionTable` component (out of scope for this feature; can be updated in a follow-up)
- eBay integration — each copy already has its own `ebay_item_id`; per-copy eBay listing continues to work unchanged

---

## Testing

- **Migration**: apply migration_43, verify constraint is gone, verify existing rows intact.
- **Repository**: add two entries with same `(collection_id, card_version_id, finish_id, condition)` — assert both rows returned with distinct `item_id`.
- **`groupEntries` unit test**: flat list with 3 copies of card A and 1 of card B → 2 groups, correct copy counts.
- **`CollectionGrid` component test**: given grouped entries, assert `×3` badge visible, assert expand shows 3 mini-rows, assert remove fires `onRemove` with correct `item_id`.
- **`AddToCollectionPopover` component test**: `existingCopies=2` → assert "You already have 2" text visible.
