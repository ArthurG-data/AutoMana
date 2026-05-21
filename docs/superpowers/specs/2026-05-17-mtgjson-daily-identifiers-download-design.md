# Design: Daily AllIdentifiers.json Download

**Date:** 2026-05-17
**Branch:** feat/mtgstock-bulk-load-range-parallel

## Problem

`staging.mtgjson.sync_uuid_mappings` already runs in the daily MTGJson chain, but it reads `AllIdentifiers.json` from a manually-placed file on disk. New cards released after the last manual drop are unresolvable during promotion — their staged price rows are silently discarded because no `card_external_identifier.mtgjson_id` row exists yet.

## Goal

Automate the download of `AllIdentifiers.json` daily, immediately before `sync_uuid_mappings`, so new card UUID→scryfallId mappings are always current before prices are staged and promoted.

## Chain: Before vs After

**Before:**
```
start_run → download.today → sync_uuid_mappings → stream_to_staging → promote → ...
```

**After:**
```
start_run → download.all_identifiers → sync_uuid_mappings → download.today → stream_to_staging → promote → ...
```

`sync_uuid_mappings` moves before the price download. It is a prerequisite for promotion, not a follow-up to the price download.

## Context Flow

The existing `run_service` dispatcher merges each step's return dict into a shared context. The new step slots in cleanly:

| Step | Returns | Consumed by |
|---|---|---|
| `download.all_identifiers` | `identifiers_filename` | `sync_uuid_mappings` |
| `sync_uuid_mappings` | `mappings_inserted` | (informational) |
| `download.today` | `file_path_prices` | `stream_to_staging` |

No signature changes to `sync_uuid_mappings` are needed — it already declares `identifiers_filename: str = "AllIdentifiers.json"` as a parameter, so the context key flows through automatically.

## Touch Points

### 1. `ApimtgjsonRepository` — new method

```python
async def fetch_all_identifiers_stream(self, dest_path: Path) -> Path:
    """Stream AllIdentifiers.json to dest_path."""
    return await self.stream_download("AllIdentifiers.json", dest_path)
```

Mirrors the existing `fetch_price_today_stream` pattern exactly.

### 2. `StorageService` — new helper

```python
def build_path(self, filename: str) -> Path:
    """Return the full resolved path for a fixed-name file (no timestamp)."""
    return self.backend.resolve_path(filename)
```

Non-timestamped variant of `build_timestamped_path`. `AllIdentifiers.json` uses a fixed name because `sync_uuid_mappings` reads it by name; no versioning or retention needed.

### 3. `data_loader.py` — new service

```python
@ServiceRegistry.register(
    "mtgjson.data.download.all_identifiers",
    api_repositories=["mtgjson"],
    storage_services=["mtgjson"],
)
async def download_all_identifiers(
    mtgjson_repository: ApimtgjsonRepository,
    storage_service: StorageService,
) -> dict:
    dest_path = storage_service.build_path("AllIdentifiers.json")
    await mtgjson_repository.fetch_all_identifiers_stream(dest_path)
    logger.info("Streamed AllIdentifiers.json to disk", extra={"file": str(dest_path)})
    return {"identifiers_filename": "AllIdentifiers.json"}
```

### 4. `pipelines.py` — chain reorder

Replace the current ordering:
```python
run_service.s("mtgjson.data.download.today"),
run_service.s("staging.mtgjson.sync_uuid_mappings"),
run_service.s("staging.mtgjson.stream_to_staging"),
```

With:
```python
run_service.s("mtgjson.data.download.all_identifiers"),
run_service.s("staging.mtgjson.sync_uuid_mappings"),
run_service.s("mtgjson.data.download.today"),
run_service.s("staging.mtgjson.stream_to_staging"),
```

## Design Decisions

- **Fixed filename, not timestamped.** `AllIdentifiers.json` is overwritten daily. No retention cleanup needed — one file, always current.
- **No new Beat entry.** Runs inside the existing `refresh-mtgjson-daily` chain at 03:00 AEST.
- **~100–200 MB plain JSON download.** Streamed to disk like the `.xz` archives. Acceptable at 03:00 AEST with no user traffic.
- **Idempotent.** The sync upserts with `ON CONFLICT DO NOTHING`; re-running the chain on the same day is safe.

## Files to Modify

1. `src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py`
2. `src/automana/core/storage.py`
3. `src/automana/core/services/app_integration/mtgjson/data_loader.py`
4. `src/automana/worker/tasks/pipelines.py`
