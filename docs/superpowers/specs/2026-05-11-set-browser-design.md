# Set Browser — Design Spec

**Date:** 2026-05-11
**Status:** Approved

## Overview

Improve the `/search` page so users can browse and select cards by set, promo type, rarity, and finish — without needing to type a specific card name. The entry point is a set browser that replaces the card grid when no set is selected.

## User Flow

1. Navigate to `/search` with no `set` param → full-area **set browser** (compact rows, newest-first)
2. Click a set row → `set=<set_code>` added to URL → browser collapses into a **selected-set banner**; card grid + filters appear below
3. Click "Change set" in the banner → `set` cleared from URL → back to set browser
4. While browsing cards, all existing filters (rarity, finish, layout, promo type) remain available in the sidebar

## Architecture

The feature is URL-state-driven. The `set` param already exists in the `/search` route schema (`z.string().optional()`). No new routes are needed.

**Data flow — set browser state (no `set` param):**
- `SetBrowser` mounts → calls `useQuery` on `GET /api/v1/set-reference/browse`
- Response: flat list of `SetBrowseItem`, sorted `released_at DESC`, non-digital only
- Renders compact row list; inline text filter narrows client-side

**Data flow — card grid state (`set` param present):**
- Browse data is always pre-fetched by `SearchPage` on mount (regardless of URL state), so `SelectedSetBanner` can resolve set metadata from the cache even when the user lands directly at `/search?set=mkm`
- `SelectedSetBanner` looks up the active set from that cache by `set_code`
- `SearchResults` fires the existing `cardInfiniteSearchQueryOptions` with `set=<set_code>` included
- Existing `SearchFilters` (rarity, finish, layout, promo type) remain active

## Backend Changes

### New endpoint

```
GET /api/v1/set-reference/browse
```

Returns a flat, unpaginated list of `SetBrowseItem`. ~700 sets fits comfortably in one response.

**Response shape per item:**
```json
{
  "set_id": "uuid",
  "set_name": "Murders at Karlov Manor",
  "set_code": "mkm",
  "set_type": "expansion",
  "card_count": 286,
  "released_at": "2024-02-09",
  "icon_svg_uri": "https://svgs.scryfall.io/sets/mkm.svg"
}
```

**Filtering:** `digital = FALSE` only (no MTGO/Arena-only sets).
**Sorting:** `released_at DESC`.

### New SQL query (`set_repository.browse`)

```sql
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
LEFT JOIN card_catalog.icon_query_ref iqr ON iqr.icon_query_id = ics.icon_query_id
WHERE vsm.digital = FALSE
ORDER BY vsm.released_at DESC
```

### New Pydantic model (`SetBrowseItem`)

Fields: `set_id: UUID`, `set_name: str`, `set_code: str`, `set_type: str`, `card_count: int`, `released_at: date`, `icon_svg_uri: str | None`.

### New service

Registered as `card_catalog.set.browse`, uses `db_repositories=["set"]`, calls `set_repository.browse()`.

### Existing card search

The existing `card_search_params` already supports `set_name`. The frontend currently passes `set` (set code) but the backend param is `set_name`. The backend `card_search_params` and card search service/repo must also accept `set_code` (or the frontend must resolve set_code → set_name using the browse cache). Preferred approach: **add `set_code` to `card_search_params`** and filter by it in the card search repository query, joining `card_catalog.sets` on `set_code`.

## Frontend Changes

### `SetBrowser` component

- Fetches sets via `useQuery(['sets-browse'], fetchSetsBrowse)` on first mount
- Renders an inline text `<input>` for client-side filtering by name or code
- Renders a scrollable list of `SetRow` items
- On click: `navigate({ search: prev => ({ ...prev, set: row.set_code }) })`

### `SetRow` component

Layout: `[icon 28px] [name bold, flex-1, truncated] [code badge] [type pill] [count monospace, right-aligned]`

- Icon: `<img src={icon_svg_uri} />` with `width=18 height=18`; fallback to a generic SVG placeholder if `icon_svg_uri` is null
- Code badge: monospace, blue-tinted background
- Type pill: accent-tinted background
- Count: muted monospace, right-aligned
- Hover: accent border + very subtle accent background tint

### `SelectedSetBanner`

Full-width sticky bar rendered between the `TopBar` and the filters+grid area.

Contents (left-to-right):
- Set icon (28px), set name (bold), code badge, type pill, card count + year
- "↩ Change set" button (right side): clears `set` from URL

Background: subtle accent-to-blue gradient (`linear-gradient(to right, rgba(accent, 0.08), rgba(blue, 0.05))`).
Border-bottom: `1px solid rgba(accent, 0.2)`.

### `SearchPage` logic update

```tsx
if (!search.set) {
  return <SetBrowser onSelect={(code) => navigate({ search: s => ({ ...s, set: code }) })} />
}
return (
  <>
    <SelectedSetBanner setCode={search.set} onClear={() => navigate({ search: s => ({ ...s, set: undefined }) })} />
    <div className={styles.layout}>
      <SearchFilters params={search} ... />
      <SearchResults ... />
    </div>
  </>
)
```

### Frontend API

New function `fetchSetsBrowse(): Promise<SetBrowseItem[]>` calling `GET /api/v1/set-reference/browse`.

New TypeScript type `SetBrowseItem` matching the backend response shape.

## UI Visual Design

**Tile style:** Compact rows (Option B) — chosen for scannability across 700+ sets.

**Row anatomy:**
```
[icon 28px] [Set Name (bold)]           [mkm] [Expansion]   286
```

**Hover state:** `border-color: rgba(accent, 0.4)`, `background: rgba(accent, 0.03)`, no transform.

**Inline filter field:** appears above the list, placeholder "Filter sets…", narrows by `set_name` or `set_code` client-side (no API call).

**Selected set banner:**
```
[⚔️ icon] [Murders at Karlov Manor]  [mkm] [Expansion]  286 cards · 2024    [↩ Change set]
```

## Error Handling

| Scenario | Behaviour |
|---|---|
| Set has no icon URI | Render generic MTG back-face SVG placeholder |
| Browse endpoint fails | Toast error + "Retry" button in set browser area |
| Inline filter finds no matches | "No sets match" message below filter input |
| Set selected, 0 cards match filters | Existing "No cards found" empty state in `SearchResults` |

## Testing

**Backend:**
- Unit: `set_repository.browse()` returns rows sorted newest-first, excludes digital sets, includes `icon_svg_uri`
- Integration: `GET /api/v1/set-reference/browse` returns 200 with correct shape

**Frontend:**
- `SetBrowser`: renders rows, inline filter narrows list, clicking a row updates URL
- `SelectedSetBanner`: displays set info, "Change set" clears `set` param
- `SearchPage`: no `set` param → `SetBrowser` shown; `set` param → banner + grid shown
