# Promo Type Faceted Filter — Search Page

**Date:** 2026-05-10
**Branch:** feat/scryfall-all-cards-illustration-fix (or new branch)
**Scope:** Search page (`/search`) only

## Problem

The search page has no way to filter by promo type. `promo_types` is already a `text[]` column on the `v_card_versions_complete` materialized view (populated by the Scryfall pipeline via `promo_card` + `promo_types_ref`), but it is never exposed to the frontend.

## Goal

Add a multi-select dropdown to the `SearchFilters` sidebar. The dropdown shows only the promo types that exist among the **current search results** (faceted). Selecting one or more types narrows the results to cards that have any of the chosen types. A display-name mapping converts raw DB codes (e.g. `buyabox`) to readable labels (e.g. "Buy a Box").

## Design

### Data flow

```
GET /api/catalog/mtg/card-reference/?q=...&promo_type=prerelease&promo_type=buyabox
  card_search_params  → promo_type: List[str] | None
  search_cards()      → card_repository.search(promo_type=[...])
    Main query        → paginated cards (existing logic + &&-filter when promo_type set)
    Facet query       → same WHERE conditions → array_agg(DISTINCT pt) AS promo_type_facets
  CardSearchResult    → cards + total_count + promo_type_facets
  PaginatedResponse   → data, pagination, facets: {"promo_types": [...]}

Frontend
  cardInfiniteSearchQueryOptions → reads body.facets?.promo_types from page 1
  search.tsx          → promoTypeFacets = data.pages[0].facets?.promo_types ?? []
  SearchFilters       → <details> dropdown, renders from promoTypeFacets
                        selecting toggles promoTypes in URL search params
                        update({ promoTypes: [...] }) → re-fetch → new facets
```

### SQL — promo_type filter

When `promo_type` is provided, append to `conditions`:

```sql
v.promo_types && $N   -- && = array overlap: card has ANY of the selected types
```

`values.append(promo_type)` — asyncpg maps a Python `list[str]` to a Postgres `text[]`.

### SQL — facet query

Run after the main query, reusing the same `conditions` list and `values` list (so facets reflect the current filter state):

```sql
SELECT array_agg(DISTINCT pt ORDER BY pt) AS promo_type_facets
FROM card_catalog.v_card_versions_complete v,
     LATERAL unnest(v.promo_types) AS t(pt)
WHERE {where_clause};
```

Returns `None` when no cards have promo types (handled as `[]`).

### GIN index

Add to `02_card_schema.sql` (after the materialized view definition):

```sql
CREATE INDEX IF NOT EXISTS idx_v_card_versions_complete_promo_types
    ON card_catalog.v_card_versions_complete USING GIN (promo_types);
```

### Display-name mapping (frontend constant)

```typescript
export const PROMO_TYPE_LABELS: Record<string, string> = {
  arenaleague:        'Arena League',
  boosterfun:         'Booster Fun',
  boxtopper:          'Box Topper',
  brawldeck:          'Brawl Deck',
  bundle:             'Bundle',
  buyabox:            'Buy a Box',
  convention:         'Convention',
  datestamped:        'Datestamped',
  draftweekend:       'Draft Weekend',
  duels:              'Duels',
  event:              'Event',
  fnm:                'Friday Night Magic',
  gameday:            'Game Day',
  gateway:            'Gateway',
  giftbox:            'Gift Box',
  gilded:             'Gilded',
  instore:            'In-Store',
  intropack:          'Intro Pack',
  jpwalker:           'JP Planeswalker',
  judgegift:          'Judge Gift',
  league:             'League',
  mediainsert:        'Media Insert',
  neonink:            'Neon Ink',
  openhouse:          'Open House',
  planeswalkerdeck:   'Planeswalker Deck',
  playerrewards:      'Player Rewards',
  playpromo:          'Play Promo',
  premiumdeck:        'Premium Deck',
  prerelease:         'Prerelease',
  promopack:          'Promo Pack',
  release:            'Release',
  serialized:         'Serialized',
  setpromo:           'Set Promo',
  starterdeck:        'Starter Deck',
  stepandcompleat:    'Step and Compleat',
  store:              'Store',
  textured:           'Textured',
  themepack:          'Theme Pack',
  tourney:            'Tourney',
  wizardsplaynetwork: 'Wizards Play Network',
}

// Fallback: title-case the raw code for unknown types
function promoLabel(code: string): string {
  return PROMO_TYPE_LABELS[code] ?? code.replace(/([a-z])([A-Z])/g, '$1 $2')
                                        .replace(/^./, c => c.toUpperCase())
}
```

### UI — dropdown

`<details>/<summary>` — no external dependency, consistent with the existing filter sidebar style.

```
▼ Promo type (2 selected)
  ☑ Buy a Box
  ☑ Prerelease
  ☐ Promo Pack
  ☐ Showcase
```

- Summary label: `"Promo type"` when none selected; `"Promo type (N selected)"` when N ≥ 1
- Hidden entirely when `promoTypeFacets` is empty (no promo cards in current results)
- Deselecting all sends `promoTypes: undefined` (removed from URL)

### Edge cases

- `promo_type_facets` is `null` from DB → coerce to `[]` in service layer
- Card has empty `promo_types` array → excluded from facet aggregation by `LATERAL unnest` (unnesting an empty array yields zero rows)
- Unknown promo type code → `promoLabel()` fallback renders a title-cased version
- `promoTypes` URL param with a value not in `promoTypeFacets` (stale URL) → backend filter still runs correctly; frontend renders the selected chip even if it's not in the facets list

## Files Changed

| File | Change |
|------|--------|
| `src/automana/database/SQL/schemas/02_card_schema.sql` | Add GIN index on `v_card_versions_complete.promo_types` |
| `src/automana/api/schemas/StandardisedQueryResponse.py` | `PaginatedResponse` gets `facets: Optional[Dict[str, List[str]]] = None` |
| `src/automana/api/dependancies/query_deps.py` | `card_search_params` adds `promo_type: Optional[List[str]] = Query(None)` |
| `src/automana/core/repositories/card_catalog/card_repository.py` | `search()` adds `promo_type` filter + facet query; returns `promo_type_facets` |
| `src/automana/core/models/card_catalog/card.py` | `CardSearchResult` adds `promo_type_facets: List[str]` |
| `src/automana/core/services/card_catalog/card_service.py` | `search_cards()` threads `promo_type` param and `promo_type_facets` through |
| `src/automana/api/routers/mtg/card_reference.py` | `list_cards` passes `facets={"promo_types": ...}` in `PaginatedResponse` |
| `src/frontend/src/features/cards/types.ts` | `CardSearchParams` adds `promoTypes?: string[]`; response adds `facets?` |
| `src/frontend/src/features/cards/api.ts` | Serialize `promoTypes` as repeated `promo_type` params; read `body.facets` |
| `src/frontend/src/routes/search.tsx` | Add `promoTypes` to `searchSchema`; extract facets; pass to `SearchFilters` |
| `src/frontend/src/features/cards/components/SearchFilters.tsx` | Add `promoTypeFacets` prop + dropdown section with `PROMO_TYPE_LABELS` map |

No new endpoints. No database migrations.

## Out of Scope

- Promo type filter on the card detail page
- Facets for other fields (rarity, finish) — `PaginatedResponse.facets` is generic but only promo types are populated now
- Promo type count badges on each facet option
