# eBay Listings Page — Design Spec

**Date:** 2026-05-09
**Scope:** Wire the existing `/listings` route Active tab to real eBay API data; add thumbnail, app badge, finish column, and inline card-name filter.

---

## Goal

Replace mock data on the Active tab of `/listings` with live eBay listings fetched from all of the user's production apps. Sold and Saved tabs remain mock for this iteration.

---

## Layout

Single unified table — all production apps merged. No per-app tabs or dropdown. App identity is shown as a colour-coded badge in an App column.

### Table columns (left → right)

| # | Column | Width | Source |
|---|--------|-------|--------|
| 1 | Thumbnail | 36px fixed | `PictureDetails.GalleryURL` |
| 2 | Card name + set/number | flex 2.2 | `Title` (parsed) + `SKU` |
| 3 | App | flex 0.9 | injected at fetch time |
| 4 | Condition | flex 0.6 | `ConditionDescription` or `ConditionID` label |
| 5 | Finish | flex 0.65 | `ItemSpecifics.NameValueList[Name==="Finish"].Value` |
| 6 | Price | flex 0.8 | `StartPrice.value` + `StartPrice.currency` |
| 7 | Watchers | flex 0.6 | `WatchCount` |
| 8 | Status | flex 0.8 | AI badge (kept from mock; real signal TBD) |

### Card name filter

A subtle underline input (~140px wide) lives inside the CARD NAME column header — it replaces the static label. Placeholder text: `card name`. Filters rows client-side on the parsed card name string. No debounce needed (client-only, instant).

### Card name link

`<a href={viewItemUrl} target="_blank" rel="noopener noreferrer">` where `viewItemUrl` comes from `ListingDetails.ViewItemURL`. Fallback: `https://www.ebay.com.au/itm/{ItemID}` when `ViewItemURL` is null.

### Thumbnail

- 28×39px, `border-radius: 3px`, `object-fit: cover`
- Source: `PictureDetails.GalleryURL` (first URL if array)
- Fallback: grey card placeholder div with `MTG` text
- Foil rows: purple border (`#a78bfa44`) + subtle box-shadow glow

### App badge

Each production app gets a consistent colour derived from its index (first: `var(--hd-blue)`, second: `#a78bfa`, third onwards: cycle). Badge shows `app_name` truncated to ~10 chars.

### Finish badge

- `"Regular"` → muted grey text, no background
- `"Foil"` → purple gradient badge (`background: linear-gradient(90deg, #a78bfa22, #60a5fa22)`, `border: 1px solid #a78bfa44`)
- Foil row also gets `background: #a78bfa05` tint on the row

---

## Data Flow

```
listings.tsx mounts
  → fetchUserApps()                          // GET /integrations/ebay/auth/apps
  → filter apps where environment === 'PRODUCTION'
  → Promise.all(apps.map(app =>
      fetchActiveListings(app.app_code)      // GET /listing/active?app_code=…
        .then(items => items.map(item => ({ ...item, appCode: app.app_code, appName: app.app_name })))
    ))
  → flatten → setListings(merged)
```

Loading state: skeleton rows (3 placeholder rows with grey shimmer) while fetching.

Error state: if an app fetch fails, that app's listings are skipped silently; a dismissible warning banner appears: "Could not load listings for [app name]."

---

## Frontend Files

| File | Action |
|------|--------|
| `features/ebay/api.ts` | Add `fetchActiveListings(appCode, limit?, offset?)` → `EbayLiveListing[]` |
| `features/ebay/mockListings.ts` | Add `EbayLiveListing` interface (mapped from raw API response) |
| `features/ebay/components/ListingsTable.tsx` | Rewrite to accept `EbayLiveListing[]`, add thumbnail/app/finish columns, inline filter |
| `features/ebay/components/ListingsTable.module.css` | Add `.thumb`, `.thumbFoil`, `.appBadge`, `.foilBadge`, `.filterInput`, `.filterInputWrapper` |
| `routes/listings.tsx` | Wire Active tab: fetch production apps → parallel listing fetches → pass to `ListingsTable` |

---

## `EbayLiveListing` Interface

```typescript
export interface EbayLiveListing {
  itemId: string
  title: string           // raw eBay title — "Ragavan, Nimble Pilferer MH2 #138 NM MTG"
  cardName: string        // parsed: title up to first set-code token
  setInfo: string         // e.g. "MH2 #138" — parsed from title or SKU
  price: number
  currency: string
  conditionLabel: string
  finish: 'Foil' | 'Regular'
  watchCount: number
  viewItemUrl: string     // ListingDetails.ViewItemURL or fallback
  imageUrl: string | null // PictureDetails.GalleryURL
  appCode: string
  appName: string
}
```

Parsing note: `cardName` is extracted from `Title` by stripping trailing tokens that match known patterns (set code, condition, "MTG", "FOIL"). A simple regex suffix-strip is sufficient; edge-cases fall back to showing the full title.

---

## API Function Signature

```typescript
export async function fetchActiveListings(
  appCode: string,
  limit = 50,
  offset = 0,
): Promise<EbayLiveListing[]>
```

Calls `GET /listing/active?app_code={appCode}&limit={limit}&offset={offset}`, maps the `PaginatedResponse.data` items to `EbayLiveListing`.

---

## Out of Scope

- Sold and Saved tabs (remain mock)
- Pagination (first 50 listings per app is sufficient for MVP)
- AI status column wired to real signal (badge kept but static for now)
- Price delta / market comparison (no market price in the API response yet)
