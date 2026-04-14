# Scryfall Ingestion Pipeline

## Overview

The Scryfall ingestion pipeline is a daily ETL (Extract, Transform, Load) process that keeps the local card catalog in sync with the [Scryfall bulk data API](https://scryfall.com/docs/api/bulk-data). It runs as a Celery task chain (`daily_scryfall_data_pipeline`) triggered by the Beat scheduler (Australia/Sydney timezone).

The pipeline is **idempotent**: re-running the same `run_key` on a given day is safe. If a day's run already succeeded, the `start_run` query short-circuits without creating a duplicate record.

The pipeline is broken into **three logical stages**:

| Stage | Responsibility |
|---|---|
| **Stage 1 – Orchestration & Tracking** | Create the run record, resolve what needs to be downloaded |
| **Stage 2 – Raw Data Download** | Fetch sets and card bulk files from the Scryfall API to local disk |
| **Stage 3 – Database Import** | Stream the raw JSON files into the PostgreSQL card catalog |

daily Celery chain (`daily_scryfall_data_pipeline`) defined in `worker/tasks/pipelines.py`. Steps run in order via `chain()`:

| Step | Service key | What it does |
|------|-------------|--------------|
| 1 | `staging.scryfall.start_pipeline` | Creates an ops run record, returns `ingestion_run_id` |
| 2 | `staging.scryfall.get_bulk_data_uri` | Reads the Scryfall bulk manifest URI from the DB |
| 3 | `staging.scryfall.download_bulk_manifests` | Fetches the manifest JSON from the Scryfall API |
| 4 | `staging.scryfall.update_data_uri_in_ops_repository` | Diffs URIs against DB; returns only changed URIs to download |
| 5 | `staging.scryfall.download_sets` | Downloads sets JSON (skips if today's file already exists) |
| 6 | `card_catalog.set.process_large_sets_json` | Loads sets into the DB |
| 7 | `staging.scryfall.download_cards_bulk` | Stream-downloads card bulk JSON (skips if no URI changes) |
| 8 | `card_catalog.card.process_large_json` | Loads cards into the DB |
| 9 | `ops.pipeline_services.finish_run` | Marks the run as success |
| 10 | `staging.scryfall.delete_old_scryfall_folders` | Keeps the 3 most recent files, deletes older ones |

---

## Stage 1 — Orchestration & Tracking

**Relevant files:**
- [`src/automana/worker/tasks/pipelines.py`](../src/automana/worker/tasks/pipelines.py) — Celery task chain definition
- [`src/automana/core/services/app_integration/scryfall/data_loader.py`](../src/automana/core/services/app_integration/scryfall/data_loader.py) — Pipeline control services
- [`src/automana/core/repositories/ops/ops_repository.py`](../src/automana/core/repositories/ops/ops_repository.py) — Ops schema write layer

### 1.1 Run Lifecycle

Every pipeline execution is tracked in the `ops` schema using three interlocking tables:

```
ops.ingestion_runs          — one row per pipeline execution (the "run")
ops.ingestion_run_steps     — one row per named step within a run
ops.ingestion_run_metrics   — arbitrary key-value metrics attached to a run
```

A run is uniquely identified by `(pipeline_name, source_id, run_key)`. The `run_key` format is:

```
scryfall_daily:<YYYY-MM-DD>          # e.g. scryfall_daily:2026-03-29
```

This means re-triggering the pipeline on the same calendar day reuses the existing run record (via `ON CONFLICT DO UPDATE`) rather than creating a duplicate, which keeps the audit trail clean.

**Run status transitions:**

```
running → success   (normal completion)
running → failed    (any step raises an unhandled exception)
running → partial   (set manually when some batches succeeded and some failed)
```

Each step writes its own row in `ops.ingestion_run_steps` via `OpsRepository.update_run()`. The step row is upserted so re-runs overwrite prior state for that step.

### 1.2 Bulk Data URI Resolution

Before downloading anything, the pipeline checks whether Scryfall has published new bulk file URIs.

**Step: `staging.scryfall.get_bulk_data_uri`**

Reads the last-known bulk data manifest URI from:

```sql
SELECT r.api_uri
FROM ops.resources r
JOIN ops.sources s ON s.name = 'scryfall' AND r.external_type = 'bulk_data'
ORDER BY s.updated_at DESC
LIMIT 1
```

This URI points to `https://api.scryfall.com/bulk-data` (the manifest endpoint, not the actual card files). If no URI is stored yet, the step fails with `no_bulk_uri`.

**Step: `staging.scryfall.download_bulk_manifests`**

Hits the manifest URI and returns a list of available bulk files. Each manifest item includes:

| Field | Description |
|---|---|
| `type` | Bulk file type (e.g. `default_cards`, `oracle_cards`, `all_cards`) |
| `download_uri` | Direct HTTPS link to the `.json` file |
| `updated_at` | ISO-8601 timestamp of the last Scryfall update |
| `size` | Approximate compressed size in bytes |

**Step: `staging.scryfall.update_data_uri_in_ops_repository`**

Diffs the downloaded manifest against the URIs already stored in `ops.resources`. Only items whose `download_uri` has changed are returned as `uris_to_download`. This prevents re-downloading multi-GB files when Scryfall has not published new data.

> **Data quality note:** Scryfall updates bulk files once per day, typically between 03:00–06:00 UTC. Running the pipeline outside that window may result in `uris_to_download = []` and the card download step being skipped entirely. This is expected behaviour and is logged as an informational message, not an error.

---

## Stage 2 — Raw Data Download

**Relevant files:**
- [`src/automana/core/services/app_integration/scryfall/data_loader.py`](../src/automana/core/services/app_integration/scryfall/data_loader.py) — Download service functions
- [`src/automana/core/repositories/app_integration/scryfall/ApiScryfall.py`](../src/automana/core/repositories/app_integration/scryfall/ApiScryfall.py) — HTTP client for Scryfall API

### 2.0 File Naming and Storage Injection

Downloaded bulk files use the naming pattern `{run_id}_{YYYYMMDD}_{original_filename}` (e.g. `42_20240315_default-cards.json`). The cleanup step matches files with glob `*default-card*` and sorts by the date token at position 1 of the `_`-split filename.

`StorageService` (`core/storage.py`) wraps `LocalStorageBackend`. `list_directory(pattern)` passes the glob pattern to `fnmatch` for filtering. `StorageService` instances are injected via `storage_services=["scryfall"]` in the `@ServiceRegistry.register` decorator.

### 2.1 Sets Download

**Step: `staging.scryfall.download_sets`**

Downloads the complete sets list from the Scryfall REST endpoint:

```
GET https://api.scryfall.com/sets
```

**Output path:**

```
/data/scryfall/raw_files/{ingestion_run_id}/sets.json
```

**File structure (Scryfall envelope):**

```json
{
  "object": "list",
  "has_more": false,
  "data": [
    {
      "id": "uuid",
      "code": "str (3–5 char set code)",
      "name": "str",
      "set_type": "str (core | expansion | masters | ...)",
      "released_at": "YYYY-MM-DD | null",
      "card_count": int,
      "digital": bool,
      "foil_only": bool,
      "nonfoil_only": bool,
      "icon_svg_uri": "https://...",
      "search_uri": "https://...",
      "scryfall_uri": "https://..."
    }
  ]
}
```

The `data` array typically contains ~800–1000 sets. The download uses the standard JSON client (`download_data_from_url`), not the streaming client, because the sets file is small (< 1 MB).

### 2.2 Card Bulk Download

**Step: `staging.scryfall.download_cards_bulk`**

Downloads each URI in `uris_to_download` using a chunked streaming approach to handle files that can exceed 1 GB.

**Implementation details (`ScryfallAPIRepository.stream_download`):**

`stream_download` is an async context manager on the repository that owns the `aiohttp` session and response lifetime. It yields an async iterable of raw bytes chunks; the service layer is responsible for writing those chunks to storage:

```
async with repository.stream_download(url) as chunks:
    async with storage_service.open_stream(filename, "wb") as f:
        async for chunk in chunks:
            f.write(chunk)
```

This keeps the HTTP transport concern in the repository and the storage concern in the service, matching the layered architecture. The session stays open for the full duration of the download and is closed cleanly on exit (including on error).

**Output path pattern:**

```
/data/scryfall/raw_files/{ingestion_run_id}/{bulk_file_name}.json
```

Example actual path:

```
/data/scryfall/raw_files/42/default-cards-20260329090112.json
```

**Common bulk file types and sizes:**

| Scryfall type | Typical size | Description |
|---|---|---|
| `default_cards` | ~120 MB | One printing per card face; recommended for most uses |
| `oracle_cards` | ~20 MB | One entry per unique oracle ID (deduplicated) |
| `all_cards` | ~900 MB | Every printing of every card including tokens |
| `rulings` | ~10 MB | Card rulings text |

> **Data quality note:** Only URIs flagged as "changed" by Step 1.2 are downloaded. If `uris_to_download` is empty, `download_cards_bulk` returns `{"file_path_card": "NO CHANGES"}`. Stage 3 detects this sentinel value and skips processing without failing.

### 2.3 Migration Download

**Step: `staging.scryfall.download_and_load_migrations`**

Card migrations record when Scryfall reassigns or merges card IDs. This step is handled separately from the bulk files.

**Source endpoint:**

```
GET https://api.scryfall.com/migrations?page=1  (paginated)
```

Each migration record contains:

| Field | Description |
|---|---|
| `id` | UUID of the migration event |
| `migration_strategy` | `merge` or `delete` |
| `old_scryfall_id` | UUID being deprecated |
| `new_scryfall_id` | UUID to map to (null for deletions) |
| `performed_at` | ISO-8601 timestamp |
| `note` | Optional human-readable explanation |

The paginator follows `next_page` links until exhausted, then serialises all records to a tab-separated `BytesIO` buffer and bulk-loads it into the database via PostgreSQL `COPY`. This avoids row-by-row inserts for what can be tens of thousands of migration records.

### 2.4 Folder Cleanup

**Step: `staging.scryfall.delete_old_scryfall_folders`**

Runs at the end of the pipeline to keep disk usage bounded.

- Scans `/data/scryfall/raw_files/` for subdirectories (one per `ingestion_run_id`).
- Sorts by modification time, newest first.
- Deletes all but the 3 most recent run folders (`keep=3`).

Each run folder holds between 150 MB and 1 GB depending on which bulk files were updated. Keeping 3 runs provides a recovery window of roughly 3 days.

---

## Stage 3 — Database Import

**Relevant files:**
- [`src/automana/core/services/card_catalog/set_service.py`](../src/automana/core/services/card_catalog/set_service.py) — Set streaming import
- [`src/automana/core/services/card_catalog/card_service.py`](../src/automana/core/services/card_catalog/card_service.py) — Card streaming import
- [`src/automana/core/repositories/card_catalog/`](../src/automana/core/repositories/card_catalog/) — DB write layer

### 3.1 Set Import

**Step: `card_catalog.set.process_large_sets_json`**

Executed immediately after `download_sets`, before the card bulk download. Sets must be present in `card_catalog.sets` before cards are inserted (foreign key dependency).

**Streaming parser:** Uses `ijson` to parse `data.item` objects one at a time from the file, avoiding loading the full JSON into memory.

**Batch processing parameters (`ProcessingConfig`):**

| Parameter | Default | Description |
|---|---|---|
| `batch_size` | 500 | Sets per `add_many` call |
| `max_retries` | 3 | Retry attempts per batch before giving up |
| `retry_delay` | 1.0 s | Base delay; multiplied by retry count (linear backoff) |
| `skip_validation_errors` | True | Log and continue on Pydantic validation failures |

**Statistics tracked (`ProcessingStats`):**

| Field | Description |
|---|---|
| `total_sets` | Records parsed from the JSON file |
| `successful_inserts` | Records written to DB (upserts count as success) |
| `failed_inserts` | Records rejected by the DB (constraint violations, type errors) |
| `batches_processed` | Number of batch `add_many` calls completed |
| `processing_errors` | Pydantic validation failures (row skipped, counted separately) |
| `success_rate` | `successful_inserts / total_sets × 100` |
| `duration_seconds` | Wall-clock time for the full file |
| `sets_per_second` | Throughput metric |

The stats dict is written to `ops.ingestion_run_steps.notes` at step completion, giving you a per-run performance baseline in the ops tables.

**Failed sets:** When `skip_validation_errors=True`, rows that fail Pydantic validation are written to a JSONL file:

```
failed_sets_<YYYYMMDD_HHMMSS>.json
```

Each entry records the raw JSON and the exception message, enabling post-hoc root cause analysis.

### 3.2 Card Import

**Step: `card_catalog.card.process_large_json`**

The most expensive step in the pipeline. The `default_cards` bulk file contains ~75,000–90,000 card printings.

**Streaming parser:** Uses `ijson.items(f, "item")` — note the top-level JSON is an array, not an envelope object, so the prefix is `"item"` not `"data.item"` (unlike sets).

**Batch processing parameters:** Same defaults as set import (`batch_size=500`, `max_retries=3`).

**Statistics tracked (`ProcessingStats`):**

| Field | Description |
|---|---|
| `total_cards` | Records parsed from the JSON file |
| `successful_inserts` | Records accepted by the DB |
| `failed_inserts` | Records rejected by the DB |
| `skipped_inserts` | Unique constraint violations (card already exists, not an error) |
| `batches_processed` | Number of batch calls completed |
| `processing_errors` | Pydantic validation failures |
| `success_rate` | `successful_inserts / total_cards × 100` |
| `cards_per_second` | Throughput metric |

**Failed cards:** Written in JSONL format (one JSON object per line) to:

```
/data/scryfall/failed_cards/failed_cards_<YYYYMMDD_HHMMSS>.jsonl
```

Failed batches (DB-level failures after all retries exhausted) are written to:

```
/tmp/failed_batches/failed_batch_{n}_{timestamp}.json
```

**Early-exit on no changes:** If `file_path_card == "NO CHANGES"` (sentinel from Stage 2), the step logs an info message, marks the step as `success` in ops, and returns immediately without reading any file or touching the database.

### 3.3 Data Model: Card Fields

Key fields written to `card_catalog.card_version` during import:

| Field | Type | Source |
|---|---|---|
| `id` | UUID | Scryfall `id` |
| `oracle_id` | UUID | Scryfall `oracle_id` |
| `name` | text | Card name |
| `set_code` | text | Set code (FK to `card_catalog.sets`) |
| `collector_number` | text | Collector number within set |
| `rarity` | text | `common / uncommon / rare / mythic / special / bonus` |
| `colors` | text[] | WUBRG colour identifiers |
| `color_identity` | text[] | Commander colour identity |
| `mana_cost` | text | Mana cost string (e.g. `{2}{U}`) |
| `cmc` | numeric | Converted mana cost |
| `type_line` | text | Full type line |
| `oracle_text` | text | Rules text |
| `power` / `toughness` | text | P/T (text to handle `*`, `X`) |
| `digital` | bool | Whether this is a digital-only printing |
| `foil` / `nonfoil` | bool | Foil availability flags |
| `prices` | jsonb | Current market prices from Scryfall |
| `image_uris` | jsonb | Image URLs at various resolutions |

### 3.4 Import Performance Benchmarks (approximate)

| Entity | File size | Record count | Expected duration | Throughput |
|---|---|---|---|---|
| Sets | < 1 MB | ~900 | < 5 s | ~200 sets/s |
| Cards (default) | ~120 MB | ~85,000 | 3–8 min | ~200–400 cards/s |
| Cards (all) | ~900 MB | ~600,000 | 30–60 min | ~200–300 cards/s |

Throughput is primarily bound by PostgreSQL upsert latency (conflict detection on `id` PK), not CPU or network.

---

## Full Pipeline Step Sequence

```
daily_scryfall_data_pipeline (Celery chain)
│
├── 1.  staging.scryfall.start_pipeline
│        Creates ops.ingestion_runs row; returns ingestion_run_id
│
├── 2.  staging.scryfall.get_bulk_data_uri
│        Reads manifest URI from ops.resources
│
├── 3.  staging.scryfall.download_bulk_manifests
│        GET <manifest_uri> → list of bulk file descriptors
│
├── 4.  staging.scryfall.update_data_uri_in_ops_repository
│        Diffs manifest vs stored URIs → uris_to_download[]
│
├── 5.  staging.scryfall.download_sets
│        GET /sets → /data/scryfall/raw_files/{run_id}/sets.json
│
├── 6.  card_catalog.set.process_large_sets_json
│        Stream-parse sets.json → upsert into card_catalog.sets (batches of 500)
│
├── 7.  staging.scryfall.download_cards_bulk
│        Stream-download each URI in uris_to_download → raw .json files
│
├── 8.  card_catalog.card.process_large_json
│        Stream-parse cards JSON → upsert into card_catalog.card_version (batches of 500)
│
├── 9.  ops.pipeline_services.finish_run  (status="success")
│        Sets ops.ingestion_runs.ended_at, status="success"
│
└── 10. staging.scryfall.delete_old_scryfall_folders  (keep=3)
         Deletes run folders older than the 3 most recent
```

---

## Error Handling & Recovery

| Failure scenario | Behaviour |
|---|---|
| No bulk URI in DB | Step 2 fails with `no_bulk_uri`; run marked `failed` |
| Scryfall API unreachable | Steps 3/5/7 raise HTTP exception; run marked `failed`; Celery retries with exponential backoff |
| Partial card batch failure | After `max_retries`, batch is dumped to `/tmp/failed_batches/` and the step raises, marking run `failed` |
| Pydantic validation error on a row | Row skipped (counted in `processing_errors`); pipeline continues |
| Re-run same day | `start_run` detects existing successful `start` step; no-ops gracefully |

---

## Observability

- **Ops tables** — query `ops.ingestion_runs` + `ops.ingestion_run_steps` for structured step-level status.
- **Daily analytics report** — `analytics.daily_summary.generate_report` (see [`reporting_services.py`](../src/automana/core/services/analytics/reporting_services.py)) queries new sets/cards in the last 24 hours and posts a summary to Discord.
- **Structured logs** — all services use the standard Python `logging` module; log records are enriched with request/task context via `core/logging_context.py`.
- **Failed record files** — `failed_cards_*.jsonl` and `failed_sets_*.json` provide row-level debug information without blocking the pipeline.
