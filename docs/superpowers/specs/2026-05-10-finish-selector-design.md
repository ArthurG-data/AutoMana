# Finish Selector — Card Detail Page

**Date:** 2026-05-10  
**Branch:** feat/scryfall-all-cards-illustration-fix  
**Scope:** Card detail page (`/cards/$id`) only

## Problem

The card detail page hardcodes a single "Non-foil" chip regardless of which finishes are actually available for a card version. The `card_version_finish` table correctly records available finishes per card version (populated by the Scryfall upsert procedure), but this data is never surfaced to the frontend.

## Goal

Show selectable finish chips (nonfoil / foil / etched / etc.) on the card detail page, limited to the finishes actually linked to that card version in `card_version_finish`. Selecting a finish re-fetches the price chart for that finish.

## Design

### Layout

Finish chips sit under the card art (Option A), extending the existing `printChips` row. The selected chip is highlighted with `--hd-accent`. The price chart below re-fetches on selection change. The top-level `$XX.XX` price and delta row stay as-is (from the initial card fetch — finish-agnostic headline price).

### Data flow

```
Scryfall pipeline
  → upsert_card() procedure
  → card_version_finish (one row per finish per card_version_id)

GET /api/catalog/mtg/card-reference/{id}
  card_repository.get()
    correlated subquery in SELECT:
      ARRAY(SELECT LOWER(cf.code)
            FROM card_catalog.card_version_finish cvf
            JOIN card_catalog.card_finished cf ON cf.finish_id = cvf.finish_id
            WHERE cvf.card_version_id = cv.card_version_id)
      AS available_finishes
  CardDetail Pydantic model → available_finishes: Optional[List[str]]

CardDetailView (React)
  selectedFinish = useState(available_finishes[0] ?? 'nonfoil')
  chip row renders from available_finishes
  ↓ passes selectedFinish prop
PriceCharts
  cardPriceHistoryQueryOptions(card_version_id, range, selectedFinish)
  chart re-fetches when selectedFinish changes
```

### Edge cases

- `available_finishes` empty or null → treat as `['nonfoil']` in the frontend
- Single-finish cards → one chip renders, no meaningful interaction but display is correct
- Finish codes come from DB as uppercase (`NONFOIL`) → lowercased in the SQL query for consistency with existing API conventions

## Files Changed

| File | Change |
|------|--------|
| `src/automana/core/repositories/card_catalog/card_repository.py` | `get()` adds `LEFT JOIN card_version_finish + card_finished` with `ARRAY_AGG(LOWER(cf.code))` |
| `src/automana/core/models/card_catalog/card.py` | `CardDetail` gets `available_finishes: Optional[List[str]] = Field(default_factory=list)` |
| `src/frontend/src/features/cards/types.ts` | `CardDetail` gets `available_finishes?: string[]` |
| `src/frontend/src/features/cards/components/CardDetailView.tsx` | `useState` for `selectedFinish`, replace hardcoded chip with dynamic chip row, pass `selectedFinish` to `PriceCharts` |
| `src/frontend/src/features/cards/components/PriceCharts.tsx` | Accept `finish?: string` prop, pass to `cardPriceHistoryQueryOptions` |

No new endpoints, no new components, no database migrations.

## Out of Scope

- Finish chips on the search results grid
- Updating the top-level `$XX.XX` price per finish (requires a separate API call)
- Filter by finish in the search page (already exists via `SearchFilters`)
