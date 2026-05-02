# Scryfall ETL Pipeline Guide

## Overview

The Scryfall pipeline is a daily Extract-Transform-Load process that keeps the AutoMana card catalog in sync with [Scryfall's bulk data API](https://scryfall.com/docs/api/bulk-data). It downloads card metadata (rules text, artwork, printing info) and maintains the `card_catalog` schema as the source of truth for Magic: The Gathering card information.

**Key characteristics:**
- **Daily schedule:** Runs once per day via Celery Beat (Australia/Sydney timezone, 09:00 UTC)
- **Idempotent:** Re-running the same day's pipeline is safe — `start_run` short-circuits if the run already succeeded
- **Three-stage architecture:** Orchestration → Download → Database Import
- **Integrity checks:** Post-completion sanity checks for data consistency
- **Storage management:** Automatic cleanup of old Scryfall data files (keeps last 3 snapshots)

---

## Pipeline Architecture

### Data Flow Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│ Celery Beat Scheduler (daily)                                       │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│ Celery Task: daily_scryfall_data_pipeline                           │
│  (src/automana/worker/tasks/pipelines.py)                           │
└────────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
    ┌────────────┐      ┌────────────┐      ┌────────────┐
    │  Stage 1   │      │  Stage 2   │      │  Stage 3   │
    │Orchestrate │      │  Download  │      │   Import   │
    └────────────┘      └────────────┘      └────────────┘
         │                    │                    │
         ├─ start_pipeline    ├─ get_bulk_uri     ├─ process_sets
         ├─ get_bulk_uri      ├─ download_manifest├─ process_cards
         ├─ download_manifest ├─ update_db_uris   ├─ download_migrations
         └─ update_db_uris    ├─ download_sets    └─ finish_run
                              └─ download_cards   

         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  Integrity Checks   │
                    │   (read-only)       │
                    └─────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │ ops.ingestion_runs  │
                    │ (tracking/audit)    │
                    └─────────────────────┘
```

### Service Chain Definition

**File:** `src/automana/worker/tasks/pipelines.py` (lines 9-48)

```python
@shared_task(name="daily_scryfall_data_pipeline", bind=True)
def daily_scryfall_data_pipeline(self):
    """Daily Scryfall ingestion chain."""
    set_task_id(self.request.id)
    run_key = f"scryfall_daily:{datetime.utcnow().date().isoformat()}"
    
    wf = chain(
        # Stage 1: Orchestration
        run_service.s("staging.scryfall.start_pipeline",
                      pipeline_name="scryfall_daily",
                      source_name="scryfall",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("staging.scryfall.get_bulk_data_uri"),
        run_service.s("staging.scryfall.download_bulk_manifests"),
        run_service.s("staging.scryfall.update_data_uri_in_ops_repository"),
        
        # Stage 2: Download
        run_service.s("staging.scryfall.download_sets"),
        run_service.s("staging.scryfall.download_cards_bulk"),
        run_service.s("staging.scryfall.download_and_load_migrations"),
        
        # Stage 3: Import
        run_service.s("card_catalog.set.process_large_sets_json"),
        run_service.s("card_catalog.card.process_large_json"),
        run_service.s("card_catalog.card_search.refresh"),
        run_service.s("card_catalog.card_search.invalidate"),
        
        # Cleanup & validation
        run_service.s("ops.pipeline_services.finish_run", status="success"),
        run_service.s("staging.scryfall.delete_old_scryfall_folders", keep=3),
        
        # Integrity checks (non-blocking)
        run_service.s("ops.integrity.scryfall_run_diff"),
        run_service.s("ops.integrity.scryfall_integrity"),
        run_service.s("ops.integrity.public_schema_leak"),
    )
    return wf.apply_async().id
```

---

## Stage 1: Orchestration & Tracking

### 1.1 Pipeline Run Lifecycle

Every execution is tracked in the `ops` schema:

| Table | Purpose |
|-------|---------|
| `ops.ingestion_runs` | One row per pipeline execution |
| `ops.ingestion_run_steps` | One row per named step (status tracking) |
| `ops.ingestion_run_metrics` | Arbitrary key-value metrics (file sizes, row counts) |
| `ops.resources` | External API endpoints (URIs, versions) |

**Run identification:**

```
run_key format: scryfall_daily:<YYYY-MM-DD>
example:      scryfall_daily:2026-04-28

This allows safe re-runs on the same day — the database
upserts rather than creating duplicates (ON CONFLICT DO UPDATE).
```

**Run status transitions:**

```
pending → running → success   (normal flow)
       → running → failed     (error/exception)
       → running → partial    (manual, some batches ok)
```

### 1.2 Start Pipeline Service

**File:** `src/automana/core/services/app_integration/scryfall/data_loader.py` (lines 25-39)

```python
@ServiceRegistry.register(path="staging.scryfall.start_pipeline",
                         db_repositories=["ops"])
async def scryfall_data_pipeline_start(
    ops_repository: OpsRepository,
    pipeline_name: str = "scryfall_daily",
    source_name: str = "scryfall",
    celery_task_id: str = None,
    run_key: str = None
) -> int:
    """
    Create or retrieve run record.
    
    Returns:
        {"ingestion_run_id": int}  — unique run identifier for this execution
    
    Idempotency:
        Calling this twice on 2026-04-28 returns the same run_id
        (via ON CONFLICT DO UPDATE in the database).
    """
    
    run_id = await ops_repository.start_run(
        pipeline_name=pipeline_name,
        source_name=source_name,
        run_key=run_key or f"{pipeline_name}_{datetime.utcnow().strftime('%Y%m%d')}",
        celery_task_id=celery_task_id,
        notes="Starting Scryfall data pipeline, scheduled daily ingestion."
    )
    
    logger.info("Scryfall pipeline run started", extra={
        "ingestion_run_id": run_id,
        "run_key": run_key
    })
    
    return {"ingestion_run_id": run_id}
```

### 1.3 Bulk Data URI Resolution

**File:** `src/automana/core/services/app_integration/scryfall/data_loader.py` (lines 42-119)

Scryfall's bulk data manifest is an index of available exports:

```python
@ServiceRegistry.register("staging.scryfall.get_bulk_data_uri",
                         db_repositories=["ops"])
async def get_scryfall_bulk_data_uri(
    ops_repository: OpsRepository,
    ingestion_run_id: int = None
) -> str:
    """
    Retrieve the manifest URI.
    
    This URI points to https://api.scryfall.com/bulk-data, which contains
    metadata about available bulk files (sets, cards, migrations, etc.).
    """
    async with track_step(ops_repository, ingestion_run_id, "get_bulk_data_uri",
                         error_code="no_bulk_uri"):
        bulk_uri = await ops_repository.get_bulk_data_uri()
        if not bulk_uri:
            raise ValueError("No bulk data URI found in the database.")
    
    return {"bulk_uri": bulk_uri}

@ServiceRegistry.register("staging.scryfall.download_bulk_manifests",
                         api_repositories=["scryfall"],
                         db_repositories=["ops"])
async def download_scryfall_bulk_manifests(
    ops_repository: OpsRepository,
    scryfall_repository: ScryfallAPIRepository,
    bulk_uri: str,
    ingestion_run_id: int = None
) -> str:
    """
    Fetch manifest JSON from Scryfall API.
    
    Returns:
        {"items": [
            {
                "type": "default_cards",
                "name": "Default Cards",
                "download_uri": "https://scryfall-api.s3.us-west-2.amazonaws.com/...",
                "size": 123456789,
                "updated_at": "2026-04-28T12:00:00Z"
            },
            ...
        ]}
    
    Common types:
        - default_cards: Default English cards (most common)
        - all_cards: All card versions (older printings)
        - oracle_cards: Oracle text only (no printing info)
    """
    async with track_step(ops_repository, ingestion_run_id, "download_bulk_manifests",
                         error_code="download_failed"):
        manifests = await scryfall_repository.download_data_from_url(bulk_uri)
        if not manifests.get("data"):
            raise ValueError("Failed to download Scryfall bulk data manifest.")
    
    logger.info("Bulk manifest downloaded", extra={
        "ingestion_run_id": ingestion_run_id,
        "item_count": len(manifests["data"])
    })
    
    return {"items": manifests["data"]}

@ServiceRegistry.register("staging.scryfall.update_data_uri_in_ops_repository",
                         db_repositories=["ops"])
async def update_data_uri_in_ops_repository(
    ops_repository: OpsRepository,
    items: dict,
    ingestion_run_id: int = None
):
    """
    Diff manifest against database; return only NEW/CHANGED items.
    
    This prevents re-downloading files that haven't changed. If today's
    default_cards URI is the same as yesterday's, we skip the ~1.5 GB download.
    
    Returns:
        {"uris_to_download": [
            {
                "type": "default_cards",
                "download_uri": "https://...",
                "updated_at": "2026-04-28T12:00:00Z"
            }
        ]}
    """
    async with track_step(ops_repository, ingestion_run_id, "update_data_uri_in_ops_repository",
                         error_code="update_failed"):
        result = await ops_repository.update_bulk_data_uri_return_new(items, ingestion_run_id)
    
    logger.info("Bulk data URIs updated in Ops repository", extra={
        "ingestion_run_id": ingestion_run_id,
        "updated_count": len(result.get("updated", [])),
        "changed_count": len(result.get("changed", []))
    })
    
    bulk_items_changed = result.get("changed", [])
    if not bulk_items_changed:
        logger.info("No changes in Scryfall bulk data URIs — skipping download",
                   extra={"ingestion_run_id": ingestion_run_id})
    
    return {"uris_to_download": bulk_items_changed}
```

---

## Stage 2: Download

### 2.1 Sets Download

**File:** `src/automana/core/services/app_integration/scryfall/data_loader.py` (lines 121-138)

```python
@ServiceRegistry.register("staging.scryfall.download_sets",
                         api_repositories=["scryfall"],
                         db_repositories=["ops"],
                         storage_services=["scryfall"])
async def download_sets(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    storage_service: StorageService = None,
) -> dict:
    """
    Download /sets endpoint (all released Magic sets).
    
    Skips if file already exists on disk (once per calendar day).
    
    Returns:
        {"filename": "scryfall_sets_20260428.json"}
    """
    filename_out = f"scryfall_sets_{datetime.utcnow().strftime('%Y%m%d')}.json"
    
    if await storage_service.file_exists(filename_out):
        logger.info("Sets file already exists — skipping download",
                   extra={"file": filename_out, "ingestion_run_id": ingestion_run_id})
    else:
        async with track_step(ops_repository, ingestion_run_id, "download_sets",
                             error_code="download_failed"):
            result = await scryfall_repository.download_data_from_url(
                "https://api.scryfall.com/sets"
            )
            await storage_service.save_json(filename_out, result.get("data", {}))
    
    return {"filename": str(filename_out)}
```

### 2.2 Cards Bulk Download

**File:** `src/automana/core/services/app_integration/scryfall/data_loader.py` (lines 140-160)

The largest file: ~1.5 GB compressed JSON containing all card definitions.

```python
@ServiceRegistry.register("staging.scryfall.download_cards_bulk",
                         api_repositories=["scryfall"],
                         db_repositories=["ops"],
                         storage_services=["scryfall"])
async def download_cards_bulk(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    uris_to_download: list[dict] | None = None,
    resource_type: str = "default_cards",
    storage_service: StorageService = None,
) -> dict:
    """
    Stream-download card bulk file (only if URI changed).
    
    Uses chunked streaming to avoid holding entire file in memory.
    Only downloads if uris_to_download contains default_cards.
    
    Returns:
        {"files_saved": [
            "1234_20260428_bulk_cards_default_cards.json.gz"
        ]}
    """
    saved = []
    
    if not uris_to_download:
        logger.info("No URIs to download — skipping bulk card download",
                   extra={"ingestion_run_id": ingestion_run_id})
        return {"files_saved": []}
    
    for item in uris_to_download:
        if item.get("type") != resource_type:
            continue
        
        uri = item.get("download_uri")
        if not uri:
            continue
        
        filename = f"{ingestion_run_id}_{datetime.utcnow().strftime('%Y%m%d')}_bulk_cards_{resource_type}.json"
        
        logger.info("Streaming bulk file", extra={
            "url": uri,
            "file": filename,
            "ingestion_run_id": ingestion_run_id
        })
        
        async with track_step(ops_repository, ingestion_run_id, f"download_cards_bulk_{resource_type}",
                             error_code="download_failed"):
            # Stream download with chunking
            async with scryfall_repository.stream_download(uri) as chunks:
                async with storage_service.open_stream(filename, "wb") as f:
                    async for chunk in chunks:
                        f.write(chunk)
        
        logger.info("Bulk file saved", extra={
            "file": filename,
            "ingestion_run_id": ingestion_run_id
        })
        
        saved.append(str(filename))
    
    return {"files_saved": saved}
```

### 2.3 Migrations Download

Card migrations track when Scryfall IDs change due to errata or duplicate resolution.

```python
@ServiceRegistry.register("staging.scryfall.download_and_load_migrations",
                         api_repositories=["scryfall"],
                         db_repositories=["ops", "card_catalog"])
async def download_and_load_migrations(
    scryfall_repository: ScryfallAPIRepository,
    ops_repository: OpsRepository,
    card_catalog_repo: CardCatalogRepository,
    ingestion_run_id: int = None
):
    """
    Fetch /migrations (paginated) and bulk-load into card_catalog.scryfall_migration.
    
    Migrations are critical for downstreams (e.g., MTGStock) that use
    old Scryfall IDs. The upsert guarantees at the repository level prevents
    duplicates; no special idempotency logic is needed in the service.
    
    Returns:
        {"migrations_loaded": int}
    """
    async with track_step(ops_repository, ingestion_run_id, "download_and_load_migrations",
                         error_code="download_failed"):
        migrations = []
        
        # Paginate through migrations endpoint
        async for migration in scryfall_repository.paginate_migrations():
            migrations.append({
                "old_scryfall_id": migration.get("old_scryfall_id"),
                "new_scryfall_id": migration.get("new_scryfall_id"),
                "note": migration.get("note")
            })
        
        # Bulk load via COPY-to-staging + ON CONFLICT DO NOTHING
        await card_catalog_repo.upsert_migrations(migrations)
    
    logger.info("Migrations loaded", extra={
        "count": len(migrations),
        "ingestion_run_id": ingestion_run_id
    })
    
    return {"migrations_loaded": len(migrations)}
```

---

## Stage 3: Import & Processing

### 3.1 Process Sets JSON

**File:** Service layer processes the downloaded sets file into `card_catalog.set`.

```python
@ServiceRegistry.register("card_catalog.set.process_large_sets_json",
                         db_repositories=["card_catalog"],
                         storage_services=["scryfall"])
async def process_sets_json(
    card_catalog_repo: CardCatalogRepository,
    ingestion_run_id: int = None,
    filename: str = None,
    storage_service: StorageService = None
):
    """
    Stream-parse sets JSON and upsert into card_catalog.set.
    
    Schema:
        id (UUID, PK)
        scryfall_id (TEXT UNIQUE)
        code (TEXT UNIQUE) — short code (ZNR, MH2, etc.)
        name (TEXT)
        released_at (DATE)
        card_count (INT)
        
    Upsert logic: ON CONFLICT (scryfall_id) DO UPDATE
    (replaces stale metadata from prior runs)
    """
    
    # Stream JSON and parse line-by-line with ijson
    set_records = []
    
    async with storage_service.open_stream(filename, "rb") as f:
        async for record in ijson_async_parser(f, "item"):
            set_records.append({
                "scryfall_id": record["id"],
                "code": record["code"],
                "name": record["name"],
                "released_at": record.get("released_at"),
                "card_count": record.get("card_count", 0)
            })
    
    # Bulk upsert
    await card_catalog_repo.upsert_sets(set_records)
    
    logger.info("Sets processed", extra={
        "count": len(set_records),
        "ingestion_run_id": ingestion_run_id
    })
    
    return {"sets_loaded": len(set_records)}
```

### 3.2 Process Cards JSON

**File:** Largest and most critical import stage.

```python
@ServiceRegistry.register("card_catalog.card.process_large_json",
                         db_repositories=["card_catalog"],
                         storage_services=["scryfall"])
async def process_cards_json(
    card_catalog_repo: CardCatalogRepository,
    ingestion_run_id: int = None,
    files_saved: list = None,
    storage_service: StorageService = None
):
    """
    Stream-parse cards bulk JSON and upsert into card_catalog.*.
    
    Tables populated:
        card_catalog.unique_cards_ref         (platonic cards)
        card_catalog.card_version             (specific printings)
        card_catalog.card_color_identity     (denormalized)
        card_catalog.card_type_line_parsed    (parsed components)
    
    Complexity:
        - ~240,000 unique cards
        - ~2 million printings (card_version rows)
        - Denormalized fields (color identity, type components) computed on insert
        - UUID generation for both unique_cards and card_versions
        - ON CONFLICT DO UPDATE for idempotency
    
    Throughput: ~30,000 rows/sec with batched COPY
    Duration: ~70 seconds for full import
    """
    
    if not files_saved:
        logger.info("No files to process",
                   extra={"ingestion_run_id": ingestion_run_id})
        return {"cards_loaded": 0}
    
    card_file = files_saved[0]  # bulk_cards_default_cards.json
    
    total_cards = 0
    total_versions = 0
    batch_size = 5000
    
    async with track_step(card_catalog_repo, ingestion_run_id, "process_large_json",
                         error_code="parse_failed"):
        
        # Stream parse with ijson
        async with storage_service.open_stream(card_file, "rb") as f:
            batch = []
            
            async for card_record in ijson_async_parser(f, "item"):
                batch.append(card_record)
                
                if len(batch) >= batch_size:
                    # Bulk upsert this batch
                    await card_catalog_repo.upsert_cards_batch(batch)
                    total_cards += len(batch)
                    batch = []
            
            # Final partial batch
            if batch:
                await card_catalog_repo.upsert_cards_batch(batch)
                total_cards += len(batch)
    
    logger.info("Cards processed", extra={
        "unique_cards": total_cards,
        "total_printings": total_versions,
        "ingestion_run_id": ingestion_run_id
    })
    
    return {"cards_loaded": total_cards, "versions_loaded": total_versions}
```

### 3.3 Card Search Index Refresh

**File:** Maintains full-text search index for card discovery.

```python
@ServiceRegistry.register("card_catalog.card_search.refresh",
                         db_repositories=["card_catalog"])
async def refresh_card_search_index(
    card_catalog_repo: CardCatalogRepository,
    ingestion_run_id: int = None
):
    """
    Rebuild full-text search index (GiST or GIN).
    
    This makes card name/rules text searchable via PostgreSQL FTS.
    Called AFTER cards are inserted to index the new data.
    
    Query:
        SELECT id, name FROM card_catalog.unique_cards_ref
        WHERE to_tsvector('english', name || ' ' || rules_text) @@ to_tsquery('lightning')
    """
    
    async with track_step(card_catalog_repo, ingestion_run_id, "refresh_card_search",
                         error_code="index_failed"):
        # Reindex or rebuild GiST/GIN
        await card_catalog_repo.rebuild_search_index()
    
    logger.info("Card search index refreshed",
               extra={"ingestion_run_id": ingestion_run_id})
    
    return {"search_index_refreshed": True}

@ServiceRegistry.register("card_catalog.card_search.invalidate",
                         db_repositories=["card_catalog"])
async def invalidate_search_cache(
    card_catalog_repo: CardCatalogRepository,
    ingestion_run_id: int = None
):
    """
    Clear any cached search results (Redis).
    
    Ensures fresh results after card catalog update.
    """
    
    cache_key_pattern = "card_search:*"
    await redis_client.delete(cache_key_pattern)
    
    logger.info("Search cache invalidated",
               extra={"ingestion_run_id": ingestion_run_id})
    
    return {"cache_invalidated": True}
```

---

## Cleanup & Validation

### 4.1 Finish Run

```python
@ServiceRegistry.register("ops.pipeline_services.finish_run",
                         db_repositories=["ops"])
async def finish_run(
    ops_repository: OpsRepository,
    ingestion_run_id: int,
    status: str = "success",
    notes: str = None
):
    """Mark the run as complete in ops.ingestion_runs."""
    
    await ops_repository.finish_run(
        ingestion_run_id,
        status=status,
        notes=notes or "Pipeline completed successfully"
    )
    
    logger.info("Pipeline run finished", extra={
        "ingestion_run_id": ingestion_run_id,
        "status": status
    })
    
    return {"status": status}
```

### 4.2 Storage Cleanup

```python
@ServiceRegistry.register("staging.scryfall.delete_old_scryfall_folders",
                         storage_services=["scryfall"])
async def delete_old_scryfall_folders(
    storage_service: StorageService,
    ingestion_run_id: int = None,
    keep: int = 3
):
    """
    Keep only the N most recent Scryfall data files.
    
    Args:
        keep: Number of dated snapshots to retain (default 3 = ~3 days)
    
    This prevents indefinite disk growth. Scryfall files are large (~1.5 GB),
    so keeping only 3 days of data saves ~4.5 GB after each run.
    """
    
    # List all scryfall_*.json files
    all_files = await storage_service.list_files("scryfall_*.json")
    
    # Sort by modification time
    sorted_files = sorted(all_files, key=lambda f: f["modified_at"], reverse=True)
    
    # Delete older than keep
    for file_record in sorted_files[keep:]:
        await storage_service.delete_file(file_record["name"])
        logger.info("Old Scryfall file deleted", extra={
            "file": file_record["name"],
            "ingestion_run_id": ingestion_run_id
        })
    
    return {"files_deleted": len(sorted_files) - keep}
```

### 4.3 Integrity Checks

Non-blocking sanity checks run AFTER the pipeline is marked successful:

```python
@ServiceRegistry.register("ops.integrity.scryfall_run_diff",
                         db_repositories=["ops", "card_catalog"])
async def scryfall_run_diff(
    ops_repository: OpsRepository,
    card_catalog_repo: CardCatalogRepository,
    ingestion_run_id: int = None
):
    """
    Compare current run's card counts against the previous run.
    
    If counts differ wildly (> 5%), log a warning but don't fail the pipeline.
    Helps catch data quality regressions.
    """
    
    current = await card_catalog_repo.count_cards()
    previous = await ops_repository.get_previous_run_metric(
        ingestion_run_id, "cards_loaded"
    )
    
    if previous and current:
        pct_change = (current - previous) / previous * 100
        if abs(pct_change) > 5:
            logger.warning("Large card count change detected", extra={
                "previous": previous,
                "current": current,
                "pct_change": pct_change,
                "ingestion_run_id": ingestion_run_id
            })
    
    return {"current_count": current, "previous_count": previous}
```

---

## Performance Optimization

### Batch Processing

```python
# COPY staging table instead of individual INSERTs
# Throughput: ~50,000 rows/sec vs. 100 rows/sec with INSERT

async def upsert_cards_batch(self, batch: List[Dict]):
    """
    Use PostgreSQL COPY for bulk inserts.
    
    Format: CSV → stdin → asyncpg COPY
    """
    
    # Convert to CSV
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=CARD_FIELDS)
    for record in batch:
        writer.writerow(record)
    
    csv_buffer.seek(0)
    
    # COPY to staging table
    await self.connection.copy_to_table(
        "staging_cards",
        source=csv_buffer,
        format='csv',
        header=True
    )
    
    # Then upsert from staging to real table
    await self.connection.execute("""
        INSERT INTO card_catalog.unique_cards_ref (...)
        SELECT ... FROM staging_cards
        ON CONFLICT (scryfall_id) DO UPDATE SET ...
    """)
    
    await self.connection.execute("TRUNCATE staging_cards")
```

### Stream Parsing

```python
# Use ijson for memory-efficient JSON parsing
# Memory footprint: O(1) regardless of file size

import ijson

async def ijson_async_parser(file, prefix):
    """Yield parsed JSON objects without loading entire file."""
    for item in ijson.items(file, prefix):
        yield item
```

---

## Error Handling

### Step-Level Tracking

```python
async with track_step(ops_repository, ingestion_run_id, "download_cards_bulk",
                     error_code="download_failed"):
    # If exception raised here, track_step() updates the step record
    # with status="failed" and error_details={"message": str(e)}
    result = await download_cards_bulk(...)
```

### Retry Logic

The Celery chain handles retries at the `run_service` level:

```python
# In worker/main.py:
@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_service(self, service_path, prev=None, **kwargs):
    """Retry transient failures with exponential backoff."""
```

---

## Monitoring & Metrics

**Tracked metrics:**

```python
class ScryfallMetrics:
    pipeline_runs_total = Counter("scryfall_pipeline_runs_total")
    pipeline_duration_seconds = Histogram("scryfall_pipeline_duration_seconds")
    cards_loaded = Gauge("scryfall_cards_loaded")
    versions_loaded = Gauge("scryfall_versions_loaded")
    download_errors = Counter("scryfall_download_errors")
    parse_errors = Counter("scryfall_parse_errors")
    import_errors = Counter("scryfall_import_errors")
```

**Structured logging:**

```python
logger.info("scryfall_pipeline_completed", extra={
    "ingestion_run_id": 12345,
    "run_key": "scryfall_daily:2026-04-28",
    "cards_loaded": 240000,
    "versions_loaded": 1950000,
    "duration_seconds": 75.3,
    "status": "success"
})
```

---

## Related Documentation

- **SCRYFALL_PIPELINE.md** (existing): Full pipeline documentation
- **PIPELINE_TECHNICAL_DEBT.md**: Known issues and optimizations
- **HEALTH_METRICS.md**: Card catalog quality checks
- **DESIGN_PATTERNS.md**: `track_step()`, service registry patterns
