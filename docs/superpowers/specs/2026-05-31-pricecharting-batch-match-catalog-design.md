# Design: Batch `build_match_catalog` DB Queries

**Date:** 2026-05-31
**Issue:** #361
**Estimate:** S

---

## Problem

`build_match_catalog` calls `fetch_versions_by_set_and_name(set_code, card_name)` once per PriceCharting product. With 63,191 singles across 375 sets, this issues 63,191 individual asyncpg queries and takes ~13 minutes.

Each call also embeds a correlated subquery to resolve the `tcgplayer_id` `card_identifier_ref_id` — a constant value re-fetched 63,191 times.

---

## Approach: One query per set, name-grouping in Python

Maximum DB round-trips drops from **63,191 → 376** (1 ref_id lookup + 1 per set).

---

## Changes

### 1. `CardReferenceRepository` — two new query methods

**`get_tcgplayer_ref_id() -> int`**

```sql
SELECT card_identifier_ref_id
FROM   card_catalog.card_identifier_ref
WHERE  identifier_name = 'tcgplayer_id'
```

Called once before the outer set loop. Result passed into `get_all_card_versions_for_set`.

---

**`get_all_card_versions_for_set(set_code: str, tcgplayer_ref_id: int) -> dict[str, list[dict]]`**

Returns all `card_version` rows for a set with the fields the matcher needs, keyed by lowercased card name.

```sql
SELECT cv.card_version_id,
       cv.collector_number,
       cv.frame_effects,
       cv.full_art,
       bc.border_color_name,
       uc.card_name,
       cei.value AS tcgplayer_id
FROM   card_catalog.card_version cv
JOIN   card_catalog.sets s         ON s.set_id          = cv.set_id
JOIN   card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
JOIN   card_catalog.border_color_ref bc ON bc.border_color_id = cv.border_color_id
LEFT JOIN card_catalog.card_external_identifier cei
       ON  cei.card_version_id       = cv.card_version_id
       AND cei.card_identifier_ref_id = $2
WHERE  UPPER(s.set_code) = UPPER($1)
```

Return type: `dict[str, list[dict]]` — `{card_name.lower(): [row_dict, ...]}`.

CQS prefix: `get_` (read-only, no side effects).

---

### 2. `build_match_catalog` service — refactor inner loop

**Before (per product):**
```python
candidates = await card_repository.fetch_versions_by_set_and_name(set_code, card_name)
```

**After (per set):**
```python
# --- before outer loop (once) ---
tcgplayer_ref_id = await card_repository.get_tcgplayer_ref_id()

# --- inside set loop (once per set) ---
set_versions = await card_repository.get_all_card_versions_for_set(set_code, tcgplayer_ref_id)

# --- inside product loop (no DB call) ---
card_name = pc_matching.clean_card_name(product["title"])
candidates = set_versions.get(card_name.lower(), [])
```

`resolve_card_match`, `pc_matching`, and all downstream logic are **untouched**.

---

### 3. `fetch_versions_by_set_and_name` — remove

The old per-product method is now unused. Delete it from `CardReferenceRepository` to avoid dead code.

---

## Correctness guarantee

The `get_all_card_versions_for_set` query is structurally identical to the old `fetch_versions_by_set_and_name` query — same JOINs, same columns, same LEFT JOIN for tcgplayer_id. The only differences are:

- No `WHERE uc.card_name ILIKE $2` filter (filtering moves to Python)
- `tcgplayer_id` ref_id passed as a parameter instead of via correlated subquery

Python name lookup uses `.lower()` on both sides, preserving the old `ILIKE` case-insensitivity.

---

## Expected outcome

| Metric | Before | After |
|---|---|---|
| DB queries | 63,191 | 376 |
| Wall time (`build_match_catalog`) | ~13 min | < 30 s |
| Match output | baseline | identical |
