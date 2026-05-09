# Create & Edit eBay Listing — Design Spec

**Date:** 2026-05-09  
**Status:** Approved  
**Scope:** Frontend only — backend endpoints and services are already implemented.

---

## Goal

Give sellers a fluid way to create new eBay listings and reprice/edit existing ones without leaving the listings view. Both flows share the same split-panel layout pattern used by the card search page.

---

## User flows

### Create (`/listings/new`)

1. Seller clicks "New listing" in the listings page top bar → navigates to `/listings/new`.
2. Two-column layout: **left** = card catalog search (filters + card grid), **right** = blank listing form.
3. Seller searches for a card and selects one from the left column.
4. Right panel pre-fills: Title (`<CardName> [<SET>]`), card image thumbnail.
5. Seller sets Price (AUD), Qty, Condition, optionally edits Title / Description, selects app.
6. "Create listing" → `POST /api/v1/integrations/ebay/listing?app_code=<code>` with a client-generated idempotency key (`crypto.randomUUID()`).
7. Success → navigate back to `/listings` with a success toast.
8. Error → inline error message; form stays open.

### Edit (inline on `/listings`)

1. Seller clicks a row in the listings table — no page navigation occurs.
2. The page layout shifts to two columns: **left** = narrowed listings table, **right** = `ListingDetailPanel`.
3. Detail panel shows read-only data: card image, name, set, condition, price, qty, watchers, days listed, app badge.
4. Seller clicks "Edit listing" → right panel content swaps to `ListingFormPanel` in edit mode, pre-filled from the Zustand store entry.
5. "Save changes" → `PUT /api/v1/integrations/ebay/listing/<item_id>?app_code=<code>`.
6. Success → panel returns to read-only view with updated values; Zustand store entry updated.
7. Error → inline error inside the panel; form stays open.
8. "Cancel" → returns to read-only detail panel.
9. Clicking the × close button (or another row) → panel closes; table returns to full width.

---

## Architecture

### Shared component: `ListingFormPanel`

```
features/ebay/components/ListingFormPanel.tsx

props:
  mode: 'create' | 'edit'
  initialValues: Partial<ListingFormValues>
  appCode?: string          // pre-selected in edit mode
  availableApps: EbayAppSummary[]
  onSave: (values: ListingFormValues) => Promise<void>
  onCancel: () => void
  isSaving: boolean
  error: string | null
```

**Form fields:**

| Field | Type | Notes |
|-------|------|-------|
| Title | text input | Max 80 chars (eBay limit). Auto-filled on create. |
| Price | number input | AUD, two decimal places, min 0.01 |
| Quantity | integer input | Min 1 |
| Condition | dropdown | NM / LP / MP / HP / DMG mapped to eBay condition IDs |
| Description | textarea | Optional. Max 500 chars for the short form. |
| App | dropdown | Production apps only. Hidden in edit mode (app is fixed). |

**Condition → eBay condition ID mapping (Trading Card category):**

| Label | eBay Condition ID |
|-------|-------------------|
| Near Mint (NM) | 3000 |
| Lightly Played (LP) | 4000 |
| Moderately Played (MP) | 5000 |
| Heavily Played (HP) | 6000 |
| Damaged (DMG) | 7000 |

### Read-only panel: `ListingDetailPanel`

```
features/ebay/components/ListingDetailPanel.tsx

props:
  listing: EbayLiveListing
  onEdit: () => void
  onClose: () => void
```

Shows: card image (thumbnail), card name, set code, condition label, AUD price, quantity available, watchers, days listed, app badge, eBay item ID, link to view on eBay.

---

## File map

### New files

| Path | Purpose |
|------|---------|
| `routes/listings_.new.tsx` | Create listing page |
| `routes/ListingsNew.module.css` | Two-column grid layout for create page |
| `features/ebay/components/ListingFormPanel.tsx` | Shared create/edit form |
| `features/ebay/components/ListingDetailPanel.tsx` | Read-only detail panel |
| `features/ebay/components/ListingFormPanel.module.css` | Form styles |
| `features/ebay/components/ListingDetailPanel.module.css` | Detail panel styles |

### Modified files

| Path | Change |
|------|--------|
| `routes/listings.tsx` | Add `selectedId` + `panelMode` state; two-column layout when row selected; render `ListingDetailPanel` or `ListingFormPanel` on right |
| `routes/Listings.module.css` | Add `.pageWithPanel` grid variant (`1fr 400px`) |
| `features/ebay/components/ListingsTable.tsx` | Accept `selectedId?: string` + `onRowClick?: (id: string) => void`; highlight selected row |
| `features/ebay/api.ts` | Add `createListing()` and `updateListing()` |
| `features/cards/components/SearchResults.tsx` | Accept optional `onSelect?: (card: CardSummary) => void`; if provided, call it on click instead of navigating |

---

## API calls (frontend)

```ts
// Create
POST /api/v1/integrations/ebay/listing?app_code=<code>
Header: Idempotency-Key: <uuid>
Body: ItemModel (Title, StartPrice, Quantity, ConditionID, Description)

// Update
PUT /api/v1/integrations/ebay/listing/<item_id>?app_code=<code>
Body: ItemModel (ItemID + changed fields)
```

Both are already implemented in the backend. No backend changes required.

---

## State management

- `listings.tsx` holds `selectedId: string | null` and `panelMode: 'detail' | 'edit'` in local `useState`.
- The Zustand `listingsStore` already holds all loaded listings. The edit panel reads from the store by `selectedId`.
- After a successful update, the store entry for the edited listing is updated in place so the table reflects the new values without a full refetch.
- After a successful create, navigate to `/listings` — the listings page will re-fetch on mount.

---

## Error handling

| Scenario | Behaviour |
|----------|-----------|
| Create fails (eBay API error) | Inline error below the form submit button; form stays open |
| Update fails | Inline error inside the detail panel; edit form stays open |
| App has no production token | Disable "Create listing" / "Save changes"; show "App not connected" message |
| Card not found in store (direct URL to edit) | Not applicable — edit is inline only, always triggered from a loaded row |
| `SearchResults` card fetch fails | Existing empty-state handling in `SearchResults` covers this |

---

## Testing

- Unit tests for `ListingFormPanel`: field validation (price > 0, title max length, qty ≥ 1), correct payload construction, cancel callback.
- Unit tests for `ListingDetailPanel`: renders all fields, edit button calls `onEdit`, close button calls `onClose`.
- Unit tests for modified `ListingsTable`: `onRowClick` fires with correct item ID, selected row gets highlight class.
- Integration test for the create flow: select card → fill form → submit → assert `POST` called with correct body and idempotency key.
- Integration test for the edit flow: click row → detail panel appears → click Edit → form pre-filled → submit → assert `PUT` called with correct body.
