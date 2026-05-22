# MTGJson Ingestion Pipeline

## Overview

The MTGJson ingestion pipeline is a daily ETL (Extract, Transform, Load) process that fetches card price data from the [MTGJson API](https://mtgjson.com/api/v5/) and loads it into the local `pricing` schema. It runs as a Celery task chain (`daily_mtgjson_data_pipeline`) triggered by the Beat scheduler.

The pipeline is **idempotent**: re-running the same `run_key` on a given day is safe. The `start_run` query short-circuits without creating a duplicate ops record when a day's run already has a successful `start` step.

The pipeline has **four logical stages**:

| Stage | Responsibility |
|---|---|
| **Stage 1 – Orchestration & Tracking** | Create the run record in the ops schema |
| **Stage 2 – Raw Data Download** | Fetch the compressed price file from the MTGJson API and persist it to local disk |
| **Stage 3 – Stream to Staging + Promote** | Stream-decompress the `.xz` directly into `pricing.mtgjson_card_prices_staging` via asyncpg COPY, then call the batched promoter proc |
| **Stage 4 – Retention Cleanup** | Trim the on-disk `.xz` archive to a sliding window |

The Celery chain (`daily_mtgjson_data_pipeline`) is defined in `worker/tasks/pipelines.py`. Steps run in order via `chain()`:

| Step | Service key | What it does |
|------|-------------|--------------|
| 1 | `ops.pipeline_services.start_run` | Creates an `ops.ingestion_runs` record; returns `ingestion_run_id` |
| 2 | `mtgjson.data.download.today` | Streams `AllPricesToday.json.xz` from the MTGJson API to local disk |
| 3 | `staging.mtgjson.stream_to_staging` | Stream-decompresses the `.xz` and COPYs per-price rows into `pricing.mtgjson_card_prices_staging` |
| 4 | `staging.mtgjson.promote_to_price_observation` | Calls `pricing.load_price_observation_from_mtgjson_staging_batched()` to promote and delete resolved staging rows |
| 5 | `staging.mtgjson.cleanup_raw_files` | Trims `{DATA_DIR}/mtgjson/raw` to the last 29 daily snapshots; purges all dailies if a bulk `AllPrices_*.json.xz` is present |
| 6 | `ops.pipeline_services.finish_run` | Marks the run as `success` |

---

## Architectural note — why no JSONB archive

Earlier versions of this pipeline persisted the decompressed payload as a JSONB row in `pricing.mtgjson_payloads` before exploding it. That approach was dropped in **migration 15** because:

- The 90-day archive decompresses to ~1–2 GB of JSON. Inserting that as JSONB exceeded the 60 s asyncpg `command_timeout` and produced an OLTP-hostile row size (TOAST'd out-of-line, slow to scan).
- The raw `.xz` files already live on disk at `{DATA_DIR}/mtgjson/raw` — that is the canonical raw archive. Keeping a second copy in the DB was redundant.
- `pricing.process_mtgjson_payload()` is no longer needed: the Python streamer (ijson + COPY) replaces the SQL LATERAL-join fanout.

Current flow: **API → disk (.xz) → stream-decompress → COPY → staging → promote**.

---

## Registered services

Additional service keys exist in the registry but are **not part of the active Celery chain**. They are available for manual invocation or future pipelines:

| Service key | File | Purpose |
|---|---|---|
| `mtgjson.data.download.last90` | `data_loader.py` | Fetches the 90-day price history file (`AllPrices.json.xz`) |
| `staging.mtgjson.check_version` | `pipeline.py` | Idempotency gate: compares `Meta.json` version against the stored version in `ops.resources` |

---

## Beat schedule

Defined in `src/automana/worker/celeryconfig.py`:

```python
"refresh-mtgjson-daily": {
    "task": "automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline",
    "schedule": crontab(hour=9, minute=8),  # 03:00 AEST
}
```

The timezone is configured via the `CELERY_TIMEZONE` environment variable (default: `Australia/Sydney`). The Celery worker itself sets `enable_utc = False` and `timezone = "Australia/Brisbane"`.

---

## Stage 1 — Orchestration & Tracking

**Relevant files:**
- [`src/automana/worker/tasks/pipelines.py`](../src/automana/worker/tasks/pipelines.py) — Celery task chain definition
- [`src/automana/core/services/ops/pipeline_services.py`](../src/automana/core/services/ops/pipeline_services.py) — `start_run` and `finish_run` service functions
- [`src/automana/core/repositories/ops/ops_repository.py`](../src/automana/core/repositories/ops/ops_repository.py) — Ops schema write layer

### 1.1 Run lifecycle

Every pipeline execution is tracked in the `ops` schema:

```
ops.ingestion_runs          — one row per pipeline execution (the "run")
ops.ingestion_run_steps     — one row per named step within a run
ops.ingestion_run_metrics   — arbitrary key-value metrics attached to a run
```

A run is uniquely identified by `(pipeline_name, source_id, run_key)`. The `run_key` format used by this pipeline is:

```
mtgjson_daily:<YYYY-MM-DD>          # e.g. mtgjson_daily:2026-04-21
```

Re-triggering the pipeline on the same calendar day reuses the existing run record (via `ON CONFLICT DO UPDATE`) rather than creating a duplicate, keeping the audit trail clean.

**Run status transitions:**

```
running → success   (normal completion via finish_run)
running → failed    (any step raises an unhandled exception)
```

---

## Stage 2 — Raw Data Download

**Relevant files:**
- [`src/automana/core/services/app_integration/mtgjson/data_loader.py`](../src/automana/core/services/app_integration/mtgjson/data_loader.py) — Download + streaming service functions
- [`src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py`](../src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py) — HTTP client for the MTGJson API

### 2.1 Today's price download

**Step 2 — `mtgjson.data.download.today`**

Service key: `mtgjson.data.download.today`
API repository: `mtgjson` → `ApimtgjsonRepository`
Storage: `mtgjson` → `LocalStorageBackend` at `{DATA_DIR}/mtgjson/raw`

Execution flow:

1. Builds a timestamped destination path via `StorageService.build_timestamped_path("AllPricesToday.json.xz")`.
2. Calls `ApimtgjsonRepository.fetch_price_today_stream(dest_path)` which streams the response body directly to disk — no full-payload buffering in memory.
3. Returns `{"file_path_prices": "<absolute_path>"}`.

**Output path pattern:**

```
{DATA_DIR}/mtgjson/raw/AllPricesToday_<YYYYMMDD_HHMMSS>.json.xz
```

`DATA_DIR` is configured via the `DATA_DIR` environment variable (default: `/data/automana_data`). The resolved storage root for MTGJson is therefore `/data/automana_data/mtgjson/raw` by default.

### 2.2 Storage injection

The `StorageService` instance is injected by `ServiceManager._execute_service()`. When a service declares `storage_services=["mtgjson"]`, the manager resolves the logical name `"mtgjson"` through `ServiceRegistry`:

```python
ServiceRegistry.register_storage("mtgjson", backend="local", subpath="mtgjson/raw")
```

The `LocalStorageBackend` is instantiated with `base_path = Path(settings.data_dir) / "mtgjson/raw"`.

### 2.3 API client

`ApimtgjsonRepository` extends `BaseApiClient`.

| Property | Value |
|---|---|
| Base URL | `https://mtgjson.com/api/v5` |
| Default headers | `Accept: application/json`, `User-Agent: AutoMana/1.0` |
| Default timeout | 30 seconds |

Available methods:

| Method | Endpoint | Description |
|---|---|---|
| `fetch_all_prices_stream(dest)` | `GET AllPrices.json.xz` | Streams the 90-day history to disk |
| `fetch_price_today_stream(dest)` | `GET AllPricesToday.json.xz` | Streams today's prices to disk |
| `fetch_meta()` | `GET Meta.json` | Catalog version metadata (JSON) |

---

## Stage 3 — Stream to Staging + Promote

### 3.1 Streaming architecture

**Step 3 — `staging.mtgjson.stream_to_staging`**

Service key: `staging.mtgjson.stream_to_staging`
DB repository: `mtgjson` → `MtgjsonRepository`
Storage: `mtgjson` → `LocalStorageBackend`
Parameter: `file_path_prices: str` (absolute path returned by the download step)

Memory stays flat regardless of payload size (~50 MB RSS for a 2 GB decompressed document). Three components cooperate:

1. **`StorageService.iter_xz_json_kvitems(absolute_path, prefix="data")`** — opens the `.xz` with `lzma.open`, feeds bytes through `ijson.kvitems` in a daemon thread, and ships parsed `(card_uuid, card_data)` pairs back to the event loop through a bounded `queue.Queue` (backpressured at 4 items). Errors in the producer thread are captured and re-raised on the consumer side.
2. **`_iter_card_rows(card_uuid, card)`** — a pure function in `data_loader.py` that walks the MTGJson price tree
   (`card.paper.<source>.<price_type>.<finish>.<date>`) and fans out one tuple per price observation, lifting the sibling `currency` scalar onto every row derived from a given source. Malformed sub-trees are skipped, not raised — shape drift in a single card shouldn't kill the whole run.
3. **`MtgjsonRepository.copy_staging_batch(records)`** — invokes `asyncpg.Connection.copy_records_to_table` with 10,000-row batches. COPY is ~10–20× faster than `INSERT` batches for this row shape.

**Advisory lock for concurrent safety.** Before any work, the service calls:

```python
await mtgjson_repository.acquire_streaming_lock("mtgjson_stream_to_staging")
```

which executes `SELECT pg_advisory_xact_lock(hashtext($1))`. The lock is transaction-scoped, so it auto-releases on COMMIT/ROLLBACK. Cost is zero when uncontended and serializes concurrent streamers when it isn't — cheap insurance against cron + manual-trigger collisions.

Returns `{"rows_staged": <int>, "cards_seen": <int>}`.

### 3.2 Promotion

**Step 4 — `staging.mtgjson.promote_to_price_observation`**

Service key: `staging.mtgjson.promote_to_price_observation`
DB repository: `mtgjson`

A zero-argument wrapper around `pricing.load_price_observation_from_mtgjson_staging_batched()`. The proc:

- Normalises finish types (`normal` → `NONFOIL`), price sources (`tcgplayer` → `tcg`), and price types (`retail`/`market` → `sell`, `buylist`/`directlow` → `buy`).
- Processes records in windows of `batch_days` days (default 30).
- Resolves card identity via `card_catalog.card_external_identifier` where `identifier_name = 'mtgjson_id'`.
- Upserts into `pricing.price_observation` on `(ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)`.
- Deletes successfully promoted rows from staging.
- Requires a `pricing.data_provider` row with `code = 'mtgjson'` to exist.

Returns `{}`.

### 3.3 Retention cleanup

**Step 5 — `staging.mtgjson.cleanup_raw_files`**

Service key: `staging.mtgjson.cleanup_raw_files`
Storage: `mtgjson` → `LocalStorageBackend`
Parameter: `retention_days: int = 29`

Two rules, composed:

- **Sliding window.** Keep the newest `retention_days` `AllPricesToday_*.json.xz` files (lexicographic sort on the timestamp in the filename); delete the rest.
- **Bulk override.** If any `AllPrices_*.json.xz` (90-day archive) is present in the same directory, delete **all** daily snapshots — the bulk subsumes them.

Per-file delete failures are logged at `WARNING` and skipped; a single bad path cannot abort the sweep.

Returns `{"files_deleted": <int>}`.

---

## Additional registered services (not in active chain)

### `staging.mtgjson.sync_uuid_mappings` *(prerequisite — run once before first pipeline execution)*

**File:** `src/automana/core/services/app_integration/mtgjson/data_loader.py`
**Repositories:** `db_repositories=["mtgjson"]`
**Storage:** `storage_services=["mtgjson"]`
**Parameter:** `identifiers_filename: str = "AllIdentifiers.json"`

Populates `card_catalog.card_external_identifier` with `identifier_name='mtgjson_id'` rows. The promotion proc resolves each staged row's `card_uuid` (a MTGJson UUID) to a `card_version_id` by joining via these rows. Without them every staging row is unresolvable and promotion produces 0 results.

**Prerequisite:** The Scryfall catalog must be loaded first — `scryfall_id` rows in `card_external_identifier` must exist. The service bridges: `AllIdentifiers.json` → `(mtgjson_uuid, scryfallId)` pairs → join to existing scryfall rows → insert mtgjson rows.

**Input file:** `AllIdentifiers.json` (downloaded separately from `https://mtgjson.com/api/v5/AllIdentifiers.json`) must be placed at `{DATA_DIR}/mtgjson/raw/AllIdentifiers.json` before running.

Execution flow:

1. Loads `AllIdentifiers.json` via `StorageService.load_json(identifiers_filename)`.
2. Iterates `data.<mtgjson_uuid>.identifiers.scryfallId` to build `(mtgjson_uuid, scryfall_id)` pairs.
3. Calls `MtgjsonRepository.upsert_mtgjson_id_mappings(pairs)` — a single SQL statement using `UNNEST` arrays to join to existing `scryfall_id` rows and insert with `ON CONFLICT DO NOTHING`.

Returns `{"mappings_inserted": <int>}`.

**When to re-run:** After a Scryfall catalog refresh that adds new cards, or when the MTGJson `AllIdentifiers.json` is updated with new UUID→scryfallId mappings.

**Manual invocation:**

```bash
PYTHONPATH=src python -m automana.tools.cli run_service staging.mtgjson.sync_uuid_mappings
```

### `mtgjson.data.download.last90`

Streams the 90-day price history (`AllPrices.json.xz`) to disk. Returns `{"file_path_prices": "<absolute_path>"}`.

### `staging.mtgjson.check_version`

**File:** `src/automana/core/services/app_integration/mtgjson/pipeline.py`
**Repositories:** `api_repositories=["mtgjson"]`, `db_repositories=["ops"]`

An idempotency gate designed to short-circuit price downloads when MTGJson has not published a new catalog version.

Execution flow:

1. Calls `ApimtgjsonRepository.fetch_meta()` to retrieve `Meta.json`.
2. Extracts `meta["data"]["version"]` and `meta["data"]["date"]`.
3. Reads the stored version from `ops.resources` via `OpsRepository.get_mtgjson_resource_version()`:
   ```sql
   SELECT metadata->>'version' AS version
   FROM ops.resources
   WHERE canonical_key = 'mtgjson.all_printings'
   LIMIT 1
   ```
4. Compares stored vs. fetched version. If different, calls `OpsRepository.upsert_mtgjson_resource_version()`:
   ```sql
   UPDATE ops.resources
   SET metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{version}', to_jsonb($1::text)),
       updated_at_source = $2::timestamptz
   WHERE canonical_key = 'mtgjson.all_printings'
   ```
5. Returns `{"version_changed": bool, "meta_version": str}`.

> Note: the `ops.resources` row with `canonical_key = 'mtgjson.all_printings'` must exist for this service to function. It is not seeded automatically by the ops schema SQL; it must be inserted manually or via a migration.

---

## Database schema

Schema file: `src/automana/database/SQL/schemas/10_mtgjson_schema.sql`
Migration removing the JSONB archive: `src/automana/database/SQL/migrations/15_drop_mtgjson_payloads.sql`

### Tables

**`pricing.mtgjson_card_prices_staging`**

Row-per-price staging table, populated directly by `staging.mtgjson.stream_to_staging` via `COPY`.

| Column | Type | Description |
|---|---|---|
| `id` | serial (PK) | Auto-increment |
| `card_uuid` | text | MTGJson card UUID |
| `price_source` | text | Price provider (e.g. `tcgplayer`, `cardmarket`) |
| `price_type` | text | `retail`/`buylist` (normalised to `sell`/`buy` during promotion) |
| `finish_type` | text | `foil`, `nonfoil`, `etched`, etc. |
| `currency` | text | Currency code |
| `price_value` | float | Price value |
| `price_date` | date | Price observation date |
| `created_at` / `updated_at` | timestamptz | Audit timestamps |

**`pricing.mtgjson_staging`** (legacy)

An earlier flat staging table. Not written by the current pipeline services.

### Stored procedures

**`pricing.load_price_observation_from_mtgjson_staging_batched(batch_days int DEFAULT 30)`**

Promotes data from `pricing.mtgjson_card_prices_staging` into the hypertable `pricing.price_observation`. See Stage 3.2 above.

> **Note (migration 18):** Price values are capped at INT4 max (~$21.4M) via `LEAST(round(price_value * 100), 2147483647)::int` before storing as `price_cents`. MTGJson's AllPrices archive occasionally includes outlier sealed-product prices that exceed this threshold; capping prevents the batch from aborting on overflow.

---

## Full pipeline step sequence

```
daily_mtgjson_data_pipeline (Celery chain)
│
├── 1. ops.pipeline_services.start_run
│        pipeline_name="mtgjson_daily", source_name="mtgjson"
│        Creates ops.ingestion_runs row; returns ingestion_run_id
│
├── 2. mtgjson.data.download.today
│        GET https://mtgjson.com/api/v5/AllPricesToday.json.xz
│        Streams to {DATA_DIR}/mtgjson/raw/AllPricesToday_<ts>.json.xz
│        Returns file_path_prices
│
├── 3. staging.mtgjson.stream_to_staging
│        pg_advisory_xact_lock('mtgjson_stream_to_staging')
│        lzma + ijson.kvitems over "data" → tuples → COPY
│        Returns {rows_staged, cards_seen}
│
├── 4. staging.mtgjson.promote_to_price_observation
│        CALL pricing.load_price_observation_from_mtgjson_staging_batched()
│        Returns {}
│
├── 5. staging.mtgjson.cleanup_raw_files
│        Sliding window (default 29 dailies) + bulk-archive override
│        Returns {files_deleted}
│
└── 6. ops.pipeline_services.finish_run  (status="success")
         Sets ops.ingestion_runs.ended_at, status="success"
```

---

## Context propagation

The `run_service` Celery task merges each step's return dict into a shared context dict. The keys returned by each step must match the parameter names consumed by subsequent steps.

| Step | Returns | Consumed by |
|---|---|---|
| `ops.pipeline_services.start_run` | `ingestion_run_id` | `ops.pipeline_services.finish_run` |
| `mtgjson.data.download.today` | `file_path_prices` | `staging.mtgjson.stream_to_staging` |
| `staging.mtgjson.stream_to_staging` | `rows_staged`, `cards_seen` | (informational — not consumed) |
| `staging.mtgjson.promote_to_price_observation` | *(empty)* | — |
| `staging.mtgjson.cleanup_raw_files` | `files_deleted` | (informational — not consumed) |

The `run_service` dispatcher filters the context dict to only pass keys that appear in the next function's signature (via `inspect.signature`), so extra keys are safely ignored.

---

## Concurrency

Staging is a single global table; two concurrent streamers would race on it. Protection is provided at two layers:

- **Run-level dedup.** `(pipeline_name, source_id, run_key)` is unique in `ops.ingestion_runs`, and the `run_key` is day-scoped, so two triggers on the same calendar day share a single run record.
- **Streaming serialization.** `stream_to_staging` takes a `pg_advisory_xact_lock(hashtext('mtgjson_stream_to_staging'))` for the lifetime of its transaction. Concurrent streamers (same-day re-trigger, or daily cron colliding with a manual load) wait their turn rather than interleaving rows.

Correctness is further backed by the promoter's `ON CONFLICT ... DO UPDATE` semantics: duplicates that do slip through produce identical upserts, not drift.

---

## Error handling & recovery

| Failure scenario | Behaviour |
|---|---|
| MTGJson API unreachable | `fetch_price_today_stream()` raises an HTTP exception; `run_service` re-raises; Celery marks the task as `FAILED` |
| Streaming parse error | Exception raised in the ijson producer thread is captured and re-raised on the async consumer, aborting `stream_to_staging` |
| Bad cell in payload (non-numeric price, invalid date) | Skipped silently — the rest of the card still loads; malformed shape in a single card doesn't fail the run |
| Storage write failure during download | `LocalStorageBackend.save` raises; the exception propagates up |
| Re-run same day | `start_run` detects an existing successful `start` step and no-ops gracefully |
| Concurrent stream attempt | Advisory lock blocks the second caller until the first commits/rolls back |

> `run_service` is defined with `autoretry_for=(Exception,)` and `max_retries=0`, meaning no automatic retries occur. Pipeline tasks themselves must not set `autoretry_for` (per `CLAUDE.md`).

---

## Observability

- **Ops tables** — query `ops.ingestion_runs` and `ops.ingestion_run_steps` for structured run-level and step-level status.
- **Structured logs** — all service functions use `logging.getLogger(__name__)`; log records are enriched with `ingestion_run_id`, `old_version`/`new_version` (for `check_version`), `file` (for storage operations), `cards`, and `rows_staged` (for streaming).
- **TUI** — the Textual TUI (`src/automana/tools/tui/panels/celery.py`) lists `daily_mtgjson_data_pipeline` with all five steps and provides a Launch button to trigger the task manually.

---

## Module registration

MTGJson services are loaded in both the `backend` and `celery` module namespaces (defined in `src/automana/core/service_modules.py`):

```python
"automana.core.services.app_integration.mtgjson.data_loader",
"automana.core.services.app_integration.mtgjson.pipeline",
```

Repository registrations (in `src/automana/core/service_registry.py`):

| Type | Logical name | Class |
|---|---|---|
| DB repository | `"mtgjson"` | `MtgjsonRepository` |
| API repository | `"mtgjson"` | `ApimtgjsonRepository` |
| Named storage | `"mtgjson"` | `LocalStorageBackend` at `{DATA_DIR}/mtgjson/raw` |
