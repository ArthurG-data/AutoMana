# MTGJson Ingestion Pipeline

## Overview

The MTGJson ingestion pipeline is a daily ETL (Extract, Transform, Load) process that fetches card price data from the [MTGJson API](https://mtgjson.com/api/v5/) and loads it into the local `pricing` schema. It runs as a Celery task chain (`daily_mtgjson_data_pipeline`) triggered by the Beat scheduler.

The pipeline is **idempotent**: re-running the same `run_key` on a given day is safe. The `start_run` query short-circuits without creating a duplicate ops record when a day's run already has a successful `start` step.

The pipeline is broken into **two logical stages**:

| Stage | Responsibility |
|---|---|
| **Stage 1 – Orchestration & Tracking** | Create the run record in the ops schema |
| **Stage 2 – Raw Data Download** | Fetch the compressed price file from the MTGJson API and persist it to local disk |

The Celery chain (`daily_mtgjson_data_pipeline`) is defined in `worker/tasks/pipelines.py`. Steps run in order via `chain()`:

| Step | Service key | What it does |
|------|-------------|--------------|
| 1 | `ops.pipeline_services.start_run` | Creates an `ops.ingestion_runs` record; returns `ingestion_run_id` |
| 2 | `mtgjson.data.download.today` | Fetches `AllPricesToday.json.xz` from the MTGJson API and saves it to local disk |
| 3 | `ops.pipeline_services.finish_run` | Marks the run as `success` |

---

## Registered services

Three additional service keys exist in the registry but are **not part of the active Celery chain**. They are available for manual invocation or future pipelines:

| Service key | File | Purpose |
|---|---|---|
| `mtgjson.data.download.last90` | `data_loader.py` | Fetches the 90-day price history file (`AllPrices.json.xz`) |
| `staging.mtgjson.check_version` | `pipeline.py` | Idempotency gate: compares `Meta.json` version against the stored version in `ops.resources` |
| `staging.mtgjson.load_prices_to_staging` | `data_loader.py` | Loads a saved `.xz` file into `pricing.mtgjson_payloads` and expands it via `pricing.process_mtgjson_payload()` |

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
mtgjson_daily:<YYYY-MM-DD>          # e.g. mtgjson_daily:2026-04-18
```

Re-triggering the pipeline on the same calendar day reuses the existing run record (via `ON CONFLICT DO UPDATE`) rather than creating a duplicate, keeping the audit trail clean.

**Run status transitions:**

```
running → success   (normal completion via finish_run)
running → failed    (any step raises an unhandled exception)
```

**Step 1 — `ops.pipeline_services.start_run`**

Service key: `ops.pipeline_services.start_run`
Registered in: `src/automana/core/services/ops/pipeline_services.py`
DB repository: `ops`

Parameters passed from the Celery task definition:

| Parameter | Value |
|---|---|
| `pipeline_name` | `"mtgjson_daily"` |
| `source_name` | `"mtgjson"` |
| `run_key` | `"mtgjson_daily:<YYYY-MM-DD>"` |
| `celery_task_id` | Celery task UUID |

Returns `{"ingestion_run_id": <int>}`. This value propagates through the remaining chain steps via `run_service`'s context merging.

**Step 3 — `ops.pipeline_services.finish_run`**

Called with `status="success"`. Updates `ops.ingestion_runs.status`, `ended_at`, and `current_step = 'finish'`.

---

## Stage 2 — Raw Data Download

**Relevant files:**
- [`src/automana/core/services/app_integration/mtgjson/data_loader.py`](../src/automana/core/services/app_integration/mtgjson/data_loader.py) — Download service functions
- [`src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py`](../src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py) — HTTP client for the MTGJson API

### 2.1 Today's price download

**Step 2 — `mtgjson.data.download.today`**

Service key: `mtgjson.data.download.today`
API repository: `mtgjson` → `ApimtgjsonRepository`
Storage: `mtgjson` → `LocalStorageBackend` at `{DATA_DIR}/mtgjson/raw`

Execution flow:

1. Calls `ApimtgjsonRepository.fetch_price_today()`, which issues:
   ```
   GET https://mtgjson.com/api/v5/AllPricesToday.json.xz
   ```
   The response body (compressed bytes) is returned as-is.
2. Calls `StorageService.save_with_timestamp(filename="AllPricesToday.json.xz", data=card_data, file_format="xz")`.
3. The storage service builds a timestamped filename of the form `AllPricesToday_<YYYYMMDD_HHMMSS>.json.xz` and writes the raw bytes to disk using `LocalStorageBackend`.
4. Returns `{"file_path_prices": "<absolute_path>"}`.

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
| `fetch_all_prices_data()` | `GET AllPrices.json.xz` | 90-day price history (compressed) |
| `fetch_price_today()` | `GET AllPricesToday.json.xz` | Today's prices (compressed) |
| `fetch_meta()` | `GET Meta.json` | Catalog version metadata (JSON) |

The `_parse_response()` method (from `BaseApiClient`) returns the raw response bytes for `.xz` endpoints and a parsed dict for JSON endpoints.

---

## Additional registered services (not in active chain)

### `mtgjson.data.download.last90`

Fetches the 90-day price history (`AllPrices.json.xz`) and saves it as `AllPrices_<YYYYMMDD_HHMMSS>.json.xz` in the same `mtgjson/raw` storage directory.

Returns `{"file_path_prices": "<absolute_path>"}`.

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

### `staging.mtgjson.load_prices_to_staging`

**File:** `src/automana/core/services/app_integration/mtgjson/data_loader.py`
**Repositories:** `db_repositories=["mtgjson"]`, `storage_services=["mtgjson"]`
**Parameter:** `file_path_prices: str` (absolute path to the `.xz` file — matches the return key from the download steps)

Execution flow:

1. Decompresses the `.xz` file using `StorageService.load_xz_as_json(file_path_prices)` (calls `lzma.open` with UTF-8 encoding; returns a Python dict).
2. Inserts the entire JSON payload into `pricing.mtgjson_payloads`:
   ```sql
   INSERT INTO pricing.mtgjson_payloads (source, filename, payload)
   VALUES ($1, $2, $3::jsonb) RETURNING id
   ```
3. Calls the stored procedure to expand the payload into `pricing.mtgjson_card_prices_staging`:
   ```sql
   CALL pricing.process_mtgjson_payload($1::uuid)
   ```
4. Returns `{"payload_id": "<uuid>"}`.

---

## Database schema

Schema file: `src/automana/database/SQL/schemas/10_mtgjson_schema.sql`

### Tables

**`pricing.mtgjson_payloads`**

Holds the raw JSON payload as a JSONB blob.

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Generated with `gen_random_uuid()` |
| `source` | text | Provenance label (value: `"mtgjson"`) |
| `fetched_at` | timestamptz | Insertion time (default `now()`) |
| `filename` | text | Absolute path of the source file |
| `payload` | jsonb | Full decompressed JSON payload |

**`pricing.mtgjson_card_prices_staging`**

Expanded row-per-price staging table, populated by `pricing.process_mtgjson_payload()`.

| Column | Type | Description |
|---|---|---|
| `id` | serial (PK) | Auto-increment |
| `card_uuid` | text | MTGJson card UUID |
| `price_source` | text | Price provider (e.g. `tcgplayer`, `cardmarket`) |
| `price_type` | text | `retail` or `buylist` |
| `finish_type` | text | `foil`, `nonfoil`, `etched`, etc. |
| `currency` | text | Currency code |
| `price_value` | float | Price value |
| `price_date` | date | Price observation date |
| `created_at` / `updated_at` | timestamptz | Audit timestamps |

**`pricing.mtgjson_staging`** (legacy)

An earlier flat staging table. Not written by the current pipeline services.

### Stored procedures

**`pricing.process_mtgjson_payload(payload_id UUID)`**

Expands the JSONB payload in `pricing.mtgjson_payloads` into individual rows in `pricing.mtgjson_card_prices_staging`. The payload structure expected by the procedure is the `data` envelope returned by the MTGJson AllPrices/AllPricesToday endpoints:

```
payload.data.<card_uuid>.paper.<source>.<price_type>.<finish>.<date> = <price_value>
```

The procedure extracts `currency` from `source_val->>'currency'` and excludes entries where `price_type_key = 'currency'`.

**`pricing.load_price_observation_from_mtgjson_staging_batched(batch_days int DEFAULT 30)`**

A follow-on procedure (not called by the current pipeline services) that promotes data from `pricing.mtgjson_card_prices_staging` into the hypertable `pricing.price_observation`. It:

- Normalises finish types (`normal` → `NONFOIL`), price sources (`tcgplayer` → `tcg`), and price types (`retail`/`market` → `sell`, `buylist`/`directlow` → `buy`).
- Processes records in windows of `batch_days` days.
- Resolves card identity via `card_catalog.card_external_identifier` where `identifier_name = 'mtgjson_id'`.
- Upserts into `pricing.price_observation` on `(ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)`.
- Deletes successfully promoted rows from staging.
- Requires a `pricing.data_provider` row with `code = 'mtgjson'` to exist.

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
│        Saves to {DATA_DIR}/mtgjson/raw/AllPricesToday_<ts>.json.xz
│        Returns file_path_prices
│
└── 3. ops.pipeline_services.finish_run  (status="success")
         Sets ops.ingestion_runs.ended_at, status="success"
```

---

## Context propagation

The `run_service` Celery task merges each step's return dict into a shared context dict. The keys returned by each step must match the parameter names consumed by subsequent steps.

| Step | Returns | Consumed by |
|---|---|---|
| `ops.pipeline_services.start_run` | `ingestion_run_id` | `ops.pipeline_services.finish_run` |
| `mtgjson.data.download.today` | `file_path_prices` | Not consumed by `finish_run`; available for extension |

The `run_service` dispatcher filters the context dict to only pass keys that appear in the next function's signature (via `inspect.signature`), so extra keys are safely ignored.

---

## Error handling & recovery

| Failure scenario | Behaviour |
|---|---|
| MTGJson API unreachable | `fetch_price_today()` raises an HTTP exception; `run_service` re-raises; Celery marks the task as `FAILED` |
| No data returned from API | `download_mtgjson_data_last_90` / `stage_mtgjson_data` raise `ValueError("No data returned from MTGJSON repository")`; the exception propagates up |
| Storage write failure | `StorageService.save_binary()` raises; the exception propagates up |
| Re-run same day | `start_run` detects an existing successful `start` step and no-ops gracefully |
| `ops.resources` row missing for `check_version` | `OpsRepository.get_mtgjson_resource_version()` returns `None`; `version_changed` evaluates to `True` (any stored value differs from fetched); the upsert then fails silently because the `WHERE canonical_key = 'mtgjson.all_printings'` matches no row |

> `run_service` is defined with `autoretry_for=(Exception,)` and `max_retries=0`, meaning no automatic retries occur. Pipeline tasks themselves must not set `autoretry_for` (per `CLAUDE.md`).

---

## Observability

- **Ops tables** — query `ops.ingestion_runs` and `ops.ingestion_run_steps` for structured run-level and step-level status.
- **Structured logs** — all service functions use `logging.getLogger(__name__)`; log records are enriched with `ingestion_run_id`, `old_version`/`new_version` (for `check_version`), `file` (for storage operations), and `payload_id` (for staging).
- **TUI** — the Textual TUI (`src/automana/tools/tui/panels/celery.py`) lists `daily_mtgjson_data_pipeline` with its three steps and provides a Launch button to trigger the task manually.

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
