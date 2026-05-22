# Set Browser + Card Detail Redesign — Status & What's Left

**Branch:** `feat/set-browser` (15 commits ahead of `main`)
**Date:** 2026-05-21
**State:** Mid-merge with `dev` — 14 files have unresolved conflicts. Frontend tests are broken until conflicts are resolved.

---

## What's Been Built

### Card Detail Redesign (100% done on this branch)

All 15 commits span card-detail and set-browser work. The card detail is complete:

| Component | Status |
|-----------|--------|
| `CardDetailView.tsx` — Hero layout with image panel + data panel | ✅ Done |
| `GameInfoCard.tsx` — Mana cost, type line, oracle text, legalities, set info, artist | ✅ Done |
| `LegalityGrid.tsx` — 8-format legality display with pass/fail chips | ✅ Done |
| `MarketCard.tsx` — Price, finish selector, 1d/7d/30d deltas | ✅ Done |
| `SetInfoBox` (inside GameInfoCard) — Keyrune icon + promo badges | ✅ Done |
| `card_repository.get()` — Rewritten to use `v_card_versions_complete` view | ✅ Done |
| Backend model — `mana_cost`, `type_line`, `artist`, `collector_number`, `promo_types`, `legalities` added | ✅ Done |
| Frontend `CardDetail` type — All new fields added | ✅ Done |
| Tests — `CardDetailView.test.tsx`, `GameInfoCard.test.tsx`, `LegalityGrid.test.tsx`, `MarketCard.test.tsx` | ✅ Done |

### Set Browser — Backend (100% done)

| Piece | Status |
|-------|--------|
| `SetBrowseItem` model with `parent_set_code` | ✅ Done |
| `set_repository.browse()` SQL — includes `parent_set_code` join | ✅ Done |
| `card_catalog.set.browse` service registered | ✅ Done |
| `GET /api/v1/sets/browse` endpoint | ✅ Done |
| `set_code` exact filter wired into `card_repository.search()` and `card_service.search_cards()` | ✅ Done |
| Unit tests (`tests/unit/core/test_set_browse.py`) | ✅ Done |
| Integration test (`tests/integration/api/test_set_browse_endpoint.py`) | ✅ Done |

### Set Browser — Frontend (partially done, blocked by merge conflict)

| Piece | Status |
|-------|--------|
| `setBrowseQueryOptions` in `api.ts` | ✅ Done |
| `SetBrowseItem` type in `types.ts` (incl. `parent_set_code`) | ✅ Done |
| `SetCard.tsx` — Icon-focused card component | ✅ Done (on `dev`) |
| `SetCard.test.tsx` | ✅ Done (on `dev`) |
| `SelectedSetBanner.tsx` | ✅ Done |
| `SetBrowser.tsx` redesign (grouping, type filters, year/type grouping, SetCard grid) | ✅ Done (on `dev`) |
| `SetBrowser.test.tsx` | ✅ Done (on `dev`) |
| `search.tsx` wiring — SetBrowser ↔ SelectedSetBanner ↔ card results | ✅ Done |

---

## Current Problem: Merge Conflict

Someone started merging `dev` into `feat/set-browser`. The merge is incomplete — **14 files have conflict markers** and the branch is in a broken state:

```
src/automana/core/models/card_catalog/card.py
src/automana/core/repositories/card_catalog/card_repository.py
src/frontend/package-lock.json
src/frontend/package.json
src/frontend/src/features/cards/components/CardDetailView.module.css
src/frontend/src/features/cards/components/CardDetailView.tsx
src/frontend/src/features/cards/components/GameInfoCard.module.css
src/frontend/src/features/cards/components/GameInfoCard.tsx
src/frontend/src/features/cards/components/SetBrowser.module.css
src/frontend/src/features/cards/components/SetBrowser.tsx
src/frontend/src/features/cards/components/__tests__/GameInfoCard.test.tsx
src/frontend/src/main.tsx
src/frontend/src/routes/cards.$id.tsx
src/frontend/src/routes/search.tsx
```

Frontend tests are completely broken (`package.json` has conflict markers, so vitest won't even start).

### Conflict intent for each file

| File | Resolution strategy |
|------|-------------------|
| `card.py` | Keep both — `dev` likely added fields; `feat/set-browser` added different fields. Merge manually. |
| `card_repository.py` | Keep both — same as above. |
| `package.json` / `package-lock.json` | Keep `dev` version (newer deps) + re-add any packages `feat/set-browser` added (check `git diff HEAD...origin/dev -- src/frontend/package.json`). |
| `CardDetailView.tsx` / `.module.css` | `feat/set-browser` has the hero redesign; `dev` may have further polish. Keep the more complete version. |
| `GameInfoCard.tsx` / `.module.css` | Same — `feat/set-browser` created it; `dev` may have moved `LegalityGrid` inside. Check both and merge. |
| `SetBrowser.tsx` / `.module.css` | `dev` version wins — it's the full redesign with grouping, type filters, and `SetCard`. |
| `GameInfoCard.test.tsx` | Merge both test suites. |
| `main.tsx` | Likely a route registration change — add both. |
| `cards.$id.tsx` | Card detail route — keep the version using the redesigned `CardDetailView`. |
| `search.tsx` | Keep `dev` version as base; verify `SetBrowser` and `SelectedSetBanner` are wired correctly. |

---

## What's Left After Resolving Conflicts

1. **Resolve the 14 merge conflicts** — priority is getting `package.json` clean first so frontend tooling works.
2. **Run frontend tests** — `cd src/frontend && npx vitest run` should pass after resolution.
3. **Run backend tests** — `pytest tests/unit/ -q` (currently 687 passing on `dev`).
4. **Manual browser check** — verify:
   - Set browser grid loads and groups by year by default
   - Type filter pills work (expansion pre-selected)
   - Clicking a set code navigates to `/search?set=<code>`
   - `SelectedSetBanner` shows set icon + name + card count
   - Card detail page shows the redesigned hero layout, legality grid, oracle text
5. **Open PR** — `feat/set-browser` → `dev` (not directly to `main`).

---

## Quick-start commands

```bash
# Abort the current merge and start fresh (safest if conflicts are many):
git merge --abort

# Or continue resolving conflicts one by one:
git status                      # shows conflicted files
git checkout --theirs src/frontend/package.json   # take dev's version
git checkout --theirs src/frontend/package-lock.json
# For each other file: open, resolve markers, git add

# Once all resolved:
cd src/frontend && npm install   # re-install after package.json fix
npx vitest run                   # frontend tests
cd ../.. && python -m pytest tests/unit/ -q   # backend tests
git commit                       # finish the merge commit
```
