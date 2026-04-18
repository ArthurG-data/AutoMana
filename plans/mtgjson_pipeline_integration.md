# MTGJson ETL Pipeline — Integration Plan

## Current State

The `daily_mtgjson_data_pipeline` Celery task exists (`worker/tasks/pipelines.py:57`) and fires daily at 09:08 AEST, but it only downloads `AllPricesToday.json.xz` to disk — no card catalog data is loaded and no prices are inserted into the database.

---

## Proposed 11-Step Pipeline Chain

```
1.  ops.pipeline_services.start_run
2.  staging.mtgjson.check_version           ← NEW: Meta.json idempotency gate
3.  staging.mtgjson.download_all_printings  ← NEW: stream-download ~60MB ZIP
4.  staging.mtgjson.extract_printings       ← NEW: unzip + validate
5.  card_catalog.set.process_mtgjson_sets   ← NEW: upsert sets first (FK order)
6.  card_catalog.card.process_mtgjson_cards ← NEW: streaming card upsert (ijson)
7.  staging.mtgjson.download_prices_today   ← REFACTOR: add context threading
8.  staging.mtgjson.load_prices_to_staging  ← NEW: xz → JSONB → SP
9.  staging.mtgjson.load_prices_to_observations ← NEW: call existing SP
10. ops.pipeline_services.finish_run
11. staging.mtgjson.delete_old_mtgjson_folders
```

---

## Step-by-Step Specifications

### Step 1 — Start Run
Already implemented: `ops.pipeline_services.start_run` in `core/services/ops/pipeline_services.py:46`. No changes needed.

`source_name="mtgjson"` — but `ops.sources` has no `mtgjson` row yet (see Gap 1).

---

### Step 2 — Version Check (Idempotency Gate)

**New service:** `staging.mtgjson.check_version` in `core/services/app_integration/mtgjson/pipeline.py`

1. `GET https://mtgjson.com/api/v5/Meta.json` (<1 KB).
2. Parse `data.date` and `data.version`.
3. Compare against stored version in `ops.resources` for `canonical_key='mtgjson.all_printings'`.
4. If unchanged → set `version_changed = False` to short-circuit Steps 3–6.
5. Upsert the new version into `ops.resources`.

Returns: `{"version_changed": bool, "meta_version": str}`

---

### Step 3 — Download AllPrintings

**New service:** `staging.mtgjson.download_all_printings` in `core/services/app_integration/mtgjson/pipeline.py`

- If `version_changed == False`: return `{"file_path_printings": "NO CHANGES"}` sentinel.
- Otherwise: stream-download `AllPrintings.json.zip` (~60 MB) to `/data/mtgjson/raw/{ingestion_run_id}/AllPrintings.json.zip`.
- Store `sha256` and `bytes` in `ops.resource_versions` after download.

Requires new method `stream_download_zip(endpoint)` on `ApimtgjsonRepository` (mirrors `ScryfallAPIRepository.stream_download`).

Returns: `{"file_path_printings": str}`

---

### Step 4 — Extract (Unzip)

**New service:** `staging.mtgjson.extract_printings` in `core/services/app_integration/mtgjson/pipeline.py`

- Short-circuit if `file_path_printings == "NO CHANGES"`.
- Use `zipfile.ZipFile` to extract `AllPrintings.json` from the ZIP.
- Validate top-level JSON has `"data"` key before committing extraction.
- Delete the ZIP after successful extraction.

Returns: `{"file_path_printings_json": str, "set_name_map": dict}`

---

### Step 5 — Set Import

**New service:** `card_catalog.set.process_mtgjson_sets` in `core/services/card_catalog/set_service.py`

- Short-circuit if sentinel received.
- Use `ijson.kvitems(f, "data")` to stream-iterate `(set_code, set_object)` pairs.
- Map MTGJson set fields to `card_catalog.sets`:

| MTGJson | DB column | Notes |
|---|---|---|
| `code` (key) | `set_code` | Natural key |
| `name` | `set_name` | |
| `type` | `set_type_id` | Via `set_type_list_ref` lookup |
| `releaseDate` | `released_at` | Format `"YYYY-MM-DD"` |
| `isOnlineOnly` | `digital` | MTGJson name differs |
| `parentCode` | `parent_set` | Lookup by set_code |
| `isFoilOnly` | `foil_only` | |
| `isNonFoilOnly` | `nonfoil_only` | |

- Build `{set_code: set_name}` map during iteration (all ~700 sets, <1 MB).
- Upsert via `card_catalog.insert_batch_sets` — **requires SP fix** (see Gap 3).

Returns: `{"sets_stats": dict, "set_name_map": dict}`

---

### Step 6 — Card Import

**New service:** `card_catalog.card.process_mtgjson_cards` in `core/services/card_catalog/card_service.py`

**Critical:** `AllPrintings.json` is ~400–600 MB uncompressed. **Must use `ijson.kvitems(f, "data")` streaming — never `json.load()`.**

1. Stream-iterate `(set_code, set_data)` pairs.
2. For each set, iterate `set_data["cards"]`.
3. Resolve `set_name` from `set_name_map[set_code]` (O(1), no DB round-trip).
4. Transform card fields:

| MTGJson field | SP parameter | Notes |
|---|---|---|
| `name` | `p_card_name` | Direct |
| `manaValue` | `p_cmc` | Name differs — cast to INT |
| `manaCost` | `p_mana_cost` | Direct |
| `text` | `p_oracle_text` | Name differs |
| `number` | `p_collector_number` | Name differs |
| `rarity` | `p_rarity_name` | Direct |
| `borderColor` | `p_border_color` | Direct |
| `frameVersion` | `p_frame_year` | Name differs |
| `layout` | `p_layout_name` | Direct |
| `isPromo` | `p_is_promo` | Direct |
| `isOnlineOnly` | `p_is_digital` | Name differs |
| `keywords` | `p_keywords` | JSONB array |
| `colorIdentity` | `p_colors` | JSONB array |
| `artist` | `p_artist` | Wrap in array: `["Name"]` |
| `legalities` | `p_legalities` | Same structure as Scryfall |
| `identifiers.scryfallId` | `p_scryfall_id` | UUID |
| `identifiers.scryfallOracleId` | `p_oracle_id` | UUID |
| `identifiers.multiverseId` | `p_multiverse_ids` | Wrap in array |
| `identifiers.tcgplayerProductId` | `p_tcgplayer_id` | INT |
| `identifiers.cardmarketId` | `p_cardmarket_id` | INT |
| `power`/`toughness`/`loyalty` | `p_power`/etc. | Direct text |
| `imageUris` | — | NULL — MTGJson has no image URIs |
| `uuid` | → `card_external_identifier` | Store as `identifier_name='mtgjson_id'` post-insert |

5. Batch into groups of 500 and call `card_catalog.insert_full_card_version()`.
6. After each batch, insert MTGJson UUIDs into `card_catalog.card_external_identifier` with `identifier_name='mtgjson_id'`.

Returns: `{"cards_stats": dict}`

---

### Step 7 — Download Prices Today

**Refactor existing:** `staging.mtgjson.today` in `core/services/app_integration/mtgjson/data_loader.py:31`

- Add `ingestion_run_id` pass-through.
- Change return to `{"file_path_prices": str}` for context threading.
- Wrap with `track_step`.

---

### Step 8 — Load Prices to Staging

**New service:** `staging.mtgjson.load_prices_to_staging`

1. Decompress `.xz` file using `lzma.open()` (stdlib — no external deps).
2. Parse JSON.
3. Insert into `pricing.mtgjson_payloads` as JSONB with `source='mtgjson'`.
4. Call `CALL pricing.process_mtgjson_payload(payload_id)` — SP already exists in `10_mtgjson_schema.sql:36`.

Returns: `{"prices_loaded": int}`

---

### Step 9 — Promote Prices to Observations

**New service:** `staging.mtgjson.load_prices_to_observations`

Calls: `CALL pricing.load_price_observation_from_mtgjson_staging_batched(batch_days := 1)`
SP already exists in `10_mtgjson_schema.sql:66`. It normalizes finish codes, source names, transaction types, then upserts into `pricing.price_observation`.

Returns: `{"observations_upserted": int}`

---

### Steps 10–11 — Finish and Cleanup

Reuse `ops.pipeline_services.finish_run`. Add new service `staging.mtgjson.delete_old_mtgjson_folders` mirroring `staging.scryfall.delete_old_scryfall_folders` — keep 3 most recent subdirectories under `/data/mtgjson/raw/`.

---

## Pipeline Task Wiring (`worker/tasks/pipelines.py:57–72`)

```python
@shared_task(name="daily_mtgjson_data_pipeline", bind=True)
def daily_mtgjson_data_pipeline(self):
    set_task_id(self.request.id)
    run_key = f"mtgjson_daily:{datetime.utcnow().date().isoformat()}"
    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgjson_daily",
                      run_key=run_key,
                      source_name="mtgjson",
                      celery_task_id=self.request.id),
        run_service.s("staging.mtgjson.check_version"),
        run_service.s("staging.mtgjson.download_all_printings"),
        run_service.s("staging.mtgjson.extract_printings"),
        run_service.s("card_catalog.set.process_mtgjson_sets"),
        run_service.s("card_catalog.card.process_mtgjson_cards"),
        run_service.s("staging.mtgjson.download_prices_today"),
        run_service.s("staging.mtgjson.load_prices_to_staging"),
        run_service.s("staging.mtgjson.load_prices_to_observations"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
        run_service.s("staging.mtgjson.delete_old_mtgjson_folders", keep=3),
    )
    return wf.apply_async().id
```

**Context key discipline:** Each step's return dict keys must exactly match the parameter names of the downstream step (`run_service` filters by signature). No `autoretry_for` on pipeline tasks (project rule).

---

## Files to Create / Modify

| Action | File |
|---|---|
| Expand chain | `worker/tasks/pipelines.py:57–72` |
| Create services | `core/services/app_integration/mtgjson/pipeline.py` (Steps 2,3,4,8,9,11) |
| Refactor | `core/services/app_integration/mtgjson/data_loader.py` (Step 7 — context threading) |
| Add method | `core/services/card_catalog/set_service.py` (Step 5) |
| Add method | `core/services/card_catalog/card_service.py` (Step 6) |
| Fix + extend | `core/repositories/app_integration/mtgjson/Apimtgjson_repository.py` (add `stream_download_zip`) |
| Fix constructor | `core/repositories/app_integration/mtgjson/mtgjson_repository.py:6` |
| Register module | `core/service_modules.py` (add `pipeline.py` to celery + all namespaces) |
| Create migration | `database/SQL/migrations/15_mtgjson_seed_data.sql` |

---

## Gaps and Issues

### Gap 1 — `ops.sources` has no `mtgjson` row (BLOCKER)
`start_run` queries `SELECT id FROM ops.sources WHERE name = $2`. No `mtgjson` row exists in `09_ops_schema.sql`. Will fail with FK violation or silently produce a null `source_id`.

**Fix:** Migration insert.

---

### Gap 2 — `ops.sources` has no `scryfall` row either
Verify whether this row was added manually in production. Migration should cover both.

---

### Gap 3 — `insert_batch_sets` SP uses `ON CONFLICT (set_id)` only (BLOCKER for idempotency)
MTGJson sets have no UUID. The SP generates a new `uuid_generate_v4()` on each run. Repeated runs insert the same set twice (caught by `set_code UNIQUE` constraint, logged as `failed_inserts`).

**Fix:** Add `ON CONFLICT (set_code) DO UPDATE` path to `insert_batch_sets` SP in `01_set_schema.sql:188–349`, or write a dedicated MTGJson set upsert using `set_code` as natural key.

---

### Gap 4 — `card_identifier_ref` has no `'mtgjson_id'` entry (BLOCKER)
`load_price_observation_from_mtgjson_staging_batched` SP (`10_mtgjson_schema.sql:169`) requires `WHERE cir.identifier_name = 'mtgjson_id'`. Missing row causes price resolution to silently produce no results.

**Fix:** Migration insert into `card_catalog.card_identifier_ref`.

---

### Gap 5 — `pricing.data_provider` has no `'mtgjson'` row (BLOCKER)
The SP raises `RAISE EXCEPTION 'Missing pricing.data_provider row with code=mtgjson'` if absent.

**Fix:** Migration insert.

---

### Gap 6 — `MtgjsonRepository` wrong constructor signature (BLOCKER)
`mtgjson_repository.py:6`: `def __init__(self, settings)`. The `ServiceManager` instantiates DB repositories with `(conn, query_executor)`. Will crash at runtime when any service using this repo is invoked.

**Fix:** Change to `def __init__(self, conn, query_executor)` matching `AbstractDBRepository`.

---

### Gap 7 — `data_staging.py::insert_mtg_json_data` is dead code
No `@ServiceRegistry.register` decorator — never callable via `run_service`.

**Fix:** Remove the file or register the service.

---

### Gap 8 — AllPrintings.json memory requirement
~400–600 MB uncompressed. `json.load()` would OOM the worker.

**Fix:** Enforce `ijson.kvitems(f, "data")` streaming in Step 6 implementation.

---

### Gap 9 — Beat schedule fires before MTGJson publishes (data freshness)
Current: `crontab(hour=9, minute=8)` = 23:08 UTC (picks up previous day's build). MTGJson publishes at ~02:00–04:00 UTC.

**Fix:** Change to `crontab(hour=19, minute=0)` = 09:00 UTC = 19:00 AEST. Also avoids overlap with Scryfall pipeline at 08:08 AEST.

---

### Gap 10 — `ETL/mtgjson_ETL.sql` uses wrong schema name
`database/SQL/schemas/ETL/mtgjson_ETL.sql:1` creates tables in schema `prices`. All other code uses schema `pricing`.

**Fix:** Remove or fix the schema name in that file.

---

### Gap 11 — `AllPrices.json` too large for daily JSONB strategy
90-day file is ~500 MB uncompressed — unsuitable as a single JSONB row. Daily pipeline should use today-only pricing only.

**Fix:** Historical 90-day load = separate one-time migration task, not a daily pipeline step.

---

## Migration File: `database/SQL/migrations/15_mtgjson_seed_data.sql`

```sql
BEGIN;

-- ops.sources row for mtgjson
INSERT INTO ops.sources (name, base_uri, kind, rate_limit_hz)
VALUES ('mtgjson', 'https://mtgjson.com/api/v5', 'http', 1.0)
ON CONFLICT (name) DO NOTHING;

-- ops.resources row for AllPrintings
WITH src AS (SELECT id FROM ops.sources WHERE name = 'mtgjson')
INSERT INTO ops.resources (
    source_id, external_type, external_id, canonical_key,
    name, description, api_uri, metadata
)
VALUES (
    (SELECT id FROM src),
    'bulk_catalog', 'AllPrintings', 'mtgjson.all_printings',
    'MTGJson AllPrintings',
    'Complete card catalog with all printings',
    'https://mtgjson.com/api/v5/AllPrintings.json.zip',
    '{"format":"json","compression":"zip"}'::jsonb
)
ON CONFLICT (source_id, external_type, external_id, canonical_key) DO NOTHING;

-- card_identifier_ref for mtgjson_id
INSERT INTO card_catalog.card_identifier_ref (identifier_name)
VALUES ('mtgjson_id')
ON CONFLICT (identifier_name) DO NOTHING;

-- pricing.data_provider for mtgjson
INSERT INTO pricing.data_provider (code, description)
VALUES ('mtgjson', 'MTGJson bulk price data')
ON CONFLICT (code) DO NOTHING;

COMMIT;
```

---

## Error Handling

| Step | Failure mode | Behaviour |
|---|---|---|
| `check_version` | API unreachable | `track_step` marks failed; Celery retry with backoff |
| `download_all_printings` | Network error mid-stream | File incomplete on disk; retry re-downloads |
| `extract_printings` | Corrupt ZIP | Raises `BadZipFile`; pipeline stops |
| `process_mtgjson_sets` | Validation error | `skip_validation_errors=True`; error logged to JSONL; pipeline continues |
| `process_mtgjson_cards` | Batch DB failure | After `max_retries=3`, batch written to `/tmp/failed_batches/`; pipeline marked `failed` |
| `load_prices_to_staging` | SP exception | Transaction rollback; step marked `failed` |
| `load_prices_to_observations` | Missing `data_provider` row | SP raises; step fails cleanly |

---

## Idempotency

- **Run-level:** `run_key = f"mtgjson_daily:{date}"` — `start_run` deduplicates via `already_started_successfully` CTE.
- **Version-level:** Step 2 gates Steps 3–6 on `Meta.json` version change.
- **Set-level:** `ON CONFLICT (set_code)` once Gap 3 is fixed.
- **Card-level:** `ON CONFLICT (unique_card_id, set_id, collector_number) DO NOTHING` — safe to re-run.
- **Price-level:** `ON CONFLICT (...) DO UPDATE` in the existing SP — safe to re-run.
- **Resource tracking:** Store SHA-256 of downloaded ZIP in `ops.resource_versions` to skip reprocessing identical files.
