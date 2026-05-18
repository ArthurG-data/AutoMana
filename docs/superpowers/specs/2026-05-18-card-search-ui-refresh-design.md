# Card Search & Set Browser UI Refresh

**Date:** 2026-05-18  
**Status:** Approved

## Overview

Improve the card search experience with better sort controls, simplified grouping, richer filters (color, card type, price trend, upcoming), and clear visual treatment for unreleased cards in both the search results and the set browser.

---

## 1. SearchFilters sidebar

### 1.1 Sort (new section — appears first, above Group by)

Directional button pills — one active at a time:

| Button label | sort_by | sort_order |
|---|---|---|
| Name A→Z | card_name | asc |
| Newest | released_at | desc |
| Oldest | released_at | asc |
| Cheapest | price | asc |
| Priciest | price | desc |

- Default: `Name A→Z` (preserves current behavior)
- `sort_by` and `sort_order` are added to `CardSearchParams` in `types.ts` and forwarded to the API in `api.ts`
- `price` must be added to `_view_cols` in `card_repository.py`

### 1.2 Group by (simplified)

Remove "Set" and "Finish" options. Keep only:

`None` | `Rarity`

Remove the `'set'` and `'finish'` values from `GROUPINGS` in `SearchFilters.tsx`. The `CardGroupBy` union type in `types.ts` narrows to `'rarity'` only (remove `'set' | 'finish'`). `buildGroups()` in `SearchResults.tsx` keeps only the rarity branch; remove the set and finish branches.

### 1.3 Color (new section)

Multi-select pills: `W` `U` `B` `R` `G` `C` `Multi`

- **Behavior:** "includes all selected" — selecting W+U returns cards whose color identity contains both White and Blue (Azorius and 3+ color cards that include both). Selecting `Multi` returns cards with 2+ colors.
- Selecting `C` (Colorless) returns cards with an empty color identity array.
- `Multi` and single-color selections are mutually exclusive in practice; selecting both is a no-op (zero results) — no special UI guard needed.
- Adds `colors: string[]` to `CardSearchParams`. API receives `colors[]` query params.
- Backend: the single `color: str` param in `query_deps.py` already exists and maps to `AND $color = ANY(v.color_identity)`. Expand it to `colors: List[str]` (repeatable query param) and loop in the repository — one AND condition per selected color. The `color_identity` array is already projected by the view.

### 1.4 Card type (new section)

Single-select pills (one active at a time):

`Creature` | `Instant` | `Sorcery` | `Enchantment` | `Artifact` | `Land` | `Planeswalker`

- Adds `card_type: string` to `CardSearchParams`. API receives `card_type` query param.
- Backend: `card_type` filter already exists in `query_deps.py` and `card_repository.py` (matches against the `types` array). `type_line` is already projected by the view (line 105). Frontend wiring only.

### 1.5 Price trend (new section — frontend-only)

Single-select pills:

`↑ Rising` | `→ Stable` | `↓ Falling`

- **Client-side only** — filters the already-loaded `cards[]` array using `price_change_7d`:
  - Rising: `price_change_7d > 0.05` (>5%)
  - Stable: `-0.05 ≤ price_change_7d ≤ 0.05`
  - Falling: `price_change_7d < -0.05` (<-5%)
- No backend change. Stored in local component state (not in the URL search params, since it filters the client-side result set).
- Applied inside `SearchResults` or as a `useMemo` filter upstream in `search.tsx`.

### 1.6 Upcoming only (new section)

Single checkbox toggle: `Show upcoming only`

- When checked: hide cards where `released_at ≤ today`.
- Requires `released_at: string | null` added to `CardSummary` in `types.ts` and projected by the backend.
- Client-side filter (like price trend) applied to the loaded result set. Not a URL param.

### 1.7 Existing sections (unchanged)

Rarity, Finish, Layout, Promo type — remain as-is.

---

## 2. SearchResults — unreleased card price label

In `renderCard()` in `SearchResults.tsx`, replace the price display logic:

```
Before: card.price != null ? `$${card.price.toFixed(2)}` : 'N/A'

After:
  - card.price != null                          → `$X.XX`  (existing up/down color)
  - card.price == null AND released_at > today  → "Not yet released"  (amber/gold, no up/down class)
  - card.price == null AND released_at ≤ today  → "N/A"  (existing grey)
```

Requires `released_at` in `CardSummary`. Use `today` computed once at render time (`new Date().toISOString().slice(0, 10)`).

---

## 3. Set browser — upcoming set visual treatment

In `SetCard.tsx`, detect upcoming sets with `set.released_at > today`:

- **Card border:** gold/amber (`#b8860b`) instead of grey
- **Art area background tint:** subtle warm dark (`#2a2200`)
- **Badge:** small `UPCOMING` pill (top-right corner of art area, `background: #b8860b; color: #000`)
- **Release date text:** amber instead of grey

No sidebar filter change. The year-grouping in `SetBrowser` already surfaces upcoming sets at the top of the `2026` / `2027` year buckets naturally.

---

## 4. Backend changes

Most backend infrastructure already exists. The changes are small:

| Change | File | Detail |
|--------|------|--------|
| Add `price` to sortable columns | `card_repository.py` | Add `'price'` to `_view_cols` set (both collapse and non-collapse paths, lines ~532 and ~566) |
| Add `released_at` to response | `card_repository.py` + `BaseCard` model | Already projected via SET JOIN in non-collapse path (line 592). Verify it appears in `BaseCard` Pydantic model; add if missing. Also add to collapse path SELECT. |
| Expand `color` → `colors[]` | `query_deps.py` + `card_repository.py` | Change `color: Optional[str]` to `colors: Optional[List[str]]` (repeatable param). In repo, loop: one `AND $N = ANY(v.color_identity)` per color. |
| `card_type` filter | — | Already fully implemented. Frontend wiring only. |

---

## 5. Frontend file changes

| File | Change |
|------|--------|
| `features/cards/types.ts` | `CardGroupBy` → `'rarity'` only; add `sort_by`, `sort_order`, `colors`, `card_type` to `CardSearchParams`; add `released_at` to `CardSummary` |
| `features/cards/api.ts` | Forward `sort_by`, `sort_order`, `colors[]`, `card_type` to API query string |
| `features/cards/components/SearchFilters.tsx` | Remove Set/Finish from GROUPINGS; add Sort, Color, Type, Price trend, Upcoming sections |
| `features/cards/components/SearchResults.tsx` | Updated price display logic; remove finish/set branches from `buildGroups()` |
| `features/cards/components/SetCard.tsx` | Upcoming badge + gold border + amber date |
| `routes/search.tsx` | Update zod schema: narrow `group` enum to `'rarity'` only; thread `price_trend` and `upcomingOnly` local state through to `SearchResults` |

---

## 6. Out of scope

- Format legality filter (deferred)
- "Upcoming only" filter in the set browser sidebar (not needed — year grouping handles it)
- Persisting price trend / upcoming toggle in the URL (client-local state is sufficient)
