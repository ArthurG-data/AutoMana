# Search Suggestion Behavior — Design Spec

**Date:** 2026-05-10  
**Branch:** feat/scryfall-all-cards-illustration-fix  
**Scope:** Frontend only — `SearchBarWithSuggestions.tsx`

---

## Problem

Two issues with the current suggestion dropdown:

1. Selecting a suggestion navigates to `/search?q=<card_name>`, which shows a list of results instead of going directly to the selected card.
2. All suggestions are shown regardless of similarity score, producing low-relevance noise when many results are returned.

---

## Goals

- Selecting a dropdown item navigates directly to the card detail page.
- Only high-quality suggestions are shown when there are enough results to filter.

---

## Design

### 1. Navigation on selection

`handleSelectSuggestion` changes from:

```ts
navigate({ to: '/search', search: { q: suggestion.card_name } })
```

to:

```ts
navigate({ to: '/cards/$id', params: { id: suggestion.card_version_id } })
```

This applies to both mouse click and keyboard Enter (when a dropdown item is highlighted). Typing Enter without any suggestion selected continues to navigate to `/search?q=...` unchanged.

### 2. Score filtering

Two named constants at the top of `SearchBarWithSuggestions.tsx`:

```ts
const SUGGESTION_SCORE_THRESHOLD = 0.5
const SUGGESTION_MIN_COUNT = 3
```

The raw suggestions from the backend are filtered before being passed to `SuggestionsDropdown`:

```ts
const suggestions = useMemo(() => {
  const raw = data?.suggestions ?? []
  if (raw.length < SUGGESTION_MIN_COUNT) return raw
  return raw.filter(s => s.score >= SUGGESTION_SCORE_THRESHOLD)
}, [data])
```

**Rationale:**
- The backend already pre-filters to `score >= 0.3` via `word_similarity` + the `%` operator, so the floor of 0.5 is a meaningful quality step.
- When fewer than 3 suggestions are returned the search is already narrow; suppressing any would be unhelpful.
- `SuggestionsDropdown` receives the filtered list — no changes needed there.
- `CardSuggestion.score` is already typed and returned by the backend — no backend or type changes required.

---

## Files Changed

| File | Change |
|------|--------|
| `src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx` | Add constants, `useMemo` filter, change navigation target |

No changes to: `SuggestionsDropdown.tsx`, `types.ts`, backend, or routes.

---

## Out of Scope

- Displaying the score visually in the dropdown.
- Making the threshold user-configurable.
- Changing the backend suggest query or response shape.
