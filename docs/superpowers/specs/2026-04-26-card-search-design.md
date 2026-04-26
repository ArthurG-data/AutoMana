# Card Search — Design Spec
**Date:** 2026-04-26
**Branch target:** main
**Status:** Approved

---

## Goals

1. Typo-tolerant name search (fuzzy matching via pg_trgm)
2. Autocomplete / typeahead endpoint for incremental name suggestions
3. Oracle text search ("find all cards that say 'draw a card'")
4. Combined filter search (color + type + rarity + CMC + format legality in one query)
5. Redis cache to absorb repeat queries
6. Fix the per-row materialized view trigger (performance hazard during ETL bulk imports)

Non-goal: semantic / embedding-based search (pgvector). Deferred to a future spec.

---

## Architecture overview

Two-tier search:

```
autocomplete (fast)          full search (rich)
       │                            │
v_card_name_suggest          v_card_versions_complete
  (4 columns, pg_trgm)        (30+ columns, tsvector + pg_trgm)
       │                            │
CardReferenceRepository.suggest()   CardReferenceRepository.search()
       │                            │
   card_service.suggest()       card_service.search()
       │                            │
GET /card-reference/suggest    GET /card-reference/
```

Both paths go through Redis before hitting the database.

---

## Section 1 — Database layer

### 1a. pg_trgm extension + new indexes

All DDL lives in `src/automana/database/SQL/schemas/02_card_schema.sql` (the project has no separate migrations directory — schema changes go directly into the schema files so a full rebuild from scratch produces the correct state).

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Unique index required by REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_v_card_name_suggest_pk
    ON card_catalog.v_card_name_suggest (card_version_id);

-- Trigram index for autocomplete view (primary fuzzy target)
CREATE INDEX gin_trgm_idx_v_card_name_suggest
    ON card_catalog.v_card_name_suggest
    USING GIN (card_name gin_trgm_ops);

-- Trigram index for full search view (fuzzy name ranking in combined queries)
CREATE INDEX gin_trgm_idx_v_card_versions_name
    ON card_catalog.v_card_versions_complete
    USING GIN (card_name gin_trgm_ops);
```

### 1b. New `v_card_name_suggest` materialized view

Lightweight — 4 columns only. Sourced from `card_version` JOIN `unique_cards_ref` JOIN `sets_ref` JOIN `rarities_ref`. No aggregations, no JSONB, no arrays.

Columns: `card_version_id`, `card_name`, `set_code`, `rarity_name`

Lives in `src/automana/database/SQL/schemas/02_card_schema.sql`, added after the existing `v_card_versions_complete` block.

### 1c. Drop per-row trigger, add refresh procedure

The existing `trigger_refresh_card_versions()` fires on every INSERT/UPDATE/DELETE to `unique_cards_ref` and `card_version`. During a 30k-card ETL bulk import this causes 30k+ full view recomputes. Drop it.

Replace with a stored procedure:

```sql
CREATE OR REPLACE PROCEDURE card_catalog.refresh_card_search_views()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY card_catalog.v_card_versions_complete;
    REFRESH MATERIALIZED VIEW CONCURRENTLY card_catalog.v_card_name_suggest;
END;
$$;
```

Called once at the end of the Scryfall and MTGJson pipeline tasks after bulk import completes. Both Celery tasks get a `call refresh_card_search_views()` step added to their pipeline chain.

---

## Section 2 — Repository layer

File: `src/automana/core/repositories/card_catalog/card_repository.py`

### 2a. New `suggest(query, limit)` method

Queries `v_card_name_suggest` only. Uses the `%` trigram operator so PostgreSQL uses the GIN index.

```sql
SELECT card_version_id, card_name, set_code, rarity_name,
       word_similarity($1, card_name) AS score
FROM card_catalog.v_card_name_suggest
WHERE $1 % card_name
ORDER BY score DESC
LIMIT $2
```

Returns a list of `CardSuggestion` objects (new lightweight Pydantic model).

### 2b. Updated `search()` method

Replaces the ILIKE name filter with fuzzy matching. Adds oracle text search. All existing filters are backward-compatible.

**Name filter (replaces ILIKE):**
```sql
word_similarity($name, card_name) > 0.3
```
Uses the new trigram GIN index on `v_card_versions_complete`.

**New oracle text filter:**
```sql
search_vector @@ websearch_to_tsquery('english', $oracle_text)
```
Activates the existing `idx_v_card_versions_complete_search` GIN index (already present, never queried).

**New format legality filter:**
```sql
legalities->>'$format' = 'legal'
```
Uses the existing `idx_v_card_versions_complete_legalities` GIN index.

**Relevance ordering:**
When name and/or oracle_text are supplied, ORDER BY includes a relevance score. The expression is constructed dynamically by the repository method:
- `name` only: `ORDER BY word_similarity($name, card_name) DESC`
- `oracle_text` only: `ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', $oracle_text)) DESC`
- Both: `ORDER BY (word_similarity($name, card_name) + ts_rank_cd(search_vector, websearch_to_tsquery('english', $oracle_text))) DESC`
- Neither: falls back to existing `sort_by` / `sort_order` params

**New method signature parameter:** `oracle_text: str | None = None`, `format: str | None = None`. All existing parameters unchanged.

---

## Section 3 — Service and cache layer

File: `src/automana/core/services/card_catalog/card_service.py`

### Cache key strategy

| Operation | Key pattern | TTL |
|-----------|-------------|-----|
| Suggest | `card_search:suggest:{lower(q)}:{limit}` | 10 min |
| Full search | `card_search:full:{sha256(sorted_params)}` | 60 min |

Uses existing `get_from_cache` / `set_to_cache` from `src/automana/core/utils/redis_cache.py`.

### 3a. New `suggest()` service

Read-through cache: check Redis → on miss, call `CardReferenceRepository.suggest()` → serialize → store → return.

Registered as service `"card_catalog.card.suggest"`.

### 3b. `search()` service — add cache wrapper

Wrap existing `search_cards()` at `card_service.py:114-166` with the same read-through pattern. No change to search logic itself.

### 3c. New `invalidate_search_cache()` service

Scans Redis for keys matching `card_search:*` and deletes them. Called at the end of both `mtgjson_download_pipeline` and `scryfall_download_pipeline` Celery tasks, after `refresh_card_search_views()` completes.

This ensures users see new set data immediately after a pipeline run without waiting for TTL expiry.

---

## Section 4 — API layer

File: `src/automana/api/routers/mtg/card_reference.py`
File: `src/automana/api/dependancies/query_deps.py`

### 4a. New `GET /card-reference/suggest` endpoint

```
GET /card-reference/suggest?q=lightn&limit=10
```

- `q`: required, minimum length 2
- `limit`: 1–20, default 10
- Response: `[{card_version_id, card_name, set_code, rarity_name, score}]`
- No pagination — always returns a short ranked list
- Placed above the `{card_id}` path endpoint to avoid routing conflicts

Calls service `"card_catalog.card.suggest"`.

### 4b. Extended `GET /card-reference/` search

Two new optional query params added to `card_search_params()` in `query_deps.py`:

- `oracle_text: str | None` — passed to repository oracle text clause
- `format: str | None` — filters on `legalities->>'<format>' = 'legal'`

All existing params unchanged. Existing clients are not broken.

---

## New Pydantic models

File: `src/automana/core/models/card_catalog/card.py` (existing card models file)

- `CardSuggestion`: `card_version_id`, `card_name`, `set_code`, `rarity_name`, `score: float`
- `CardSuggestionResponse`: `suggestions: list[CardSuggestion]`

`CardSearchResult` (existing) gains no new fields — `oracle_text` and `format` are inputs, not outputs.

---

## Schema file changes

All changes go into `src/automana/database/SQL/schemas/02_card_schema.sql` in this order:

1. `CREATE EXTENSION IF NOT EXISTS pg_trgm` (near top, with other extensions)
2. DDL for `v_card_name_suggest` materialized view
3. Unique index on `v_card_name_suggest(card_version_id)` (required for CONCURRENTLY)
4. Trigram GIN indexes on both views
5. `DROP TRIGGER` / `DROP FUNCTION` for the per-row refresh trigger
6. `CREATE OR REPLACE PROCEDURE card_catalog.refresh_card_search_views()`

A full rebuild from scratch will produce the correct state with no migration step required.

---

## ETL integration points

| Pipeline | Where to add |
|----------|-------------|
| `scryfall_download_pipeline` | After bulk card insert step: call `refresh_card_search_views()`, then `invalidate_search_cache()` |
| `mtgjson_download_pipeline` | Same pattern |

No changes to the MTGStock pipeline (it doesn't import card catalog data).

---

## What is NOT changing

- Existing `GET /card-reference/` response shape
- Existing `GET /card-reference/{card_id}` endpoint
- `CardSearchResult` model
- All existing indexes on `v_card_versions_complete`
- `insert_full_card_version()` and `insert_batch_card_versions()` stored procedures
- Pagination and sorting logic

---

## Out of scope

- pgvector / semantic "find similar cards" search
- GraphQL
- Elasticsearch or external search engines
- Search analytics / logging of queries
