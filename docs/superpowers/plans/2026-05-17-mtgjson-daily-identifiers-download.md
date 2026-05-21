# MTGJson Daily AllIdentifiers.json Download — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate daily download of `AllIdentifiers.json` from the MTGJson API and run it before the price download so new card UUID→scryfallId mappings are always current.

**Architecture:** Add a `mtgjson.data.download.all_identifiers` service that streams `AllIdentifiers.json` to a fixed path on disk, then reorder the existing `daily_mtgjson_data_pipeline` chain so identifier download → UUID sync → price download → stream → promote. The context key `identifiers_filename` flows naturally from the new step into the existing `sync_uuid_mappings` step via the `run_service` context-merge mechanism — no signature changes required.

**Tech Stack:** Python 3.12, asyncio, httpx (streaming), `ServiceRegistry`, `StorageService`, Celery chain, pytest + `unittest.mock.AsyncMock`

---

## File map

| Action | File |
|--------|------|
| Modify | `src/automana/core/storage.py` |
| Modify | `src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py` |
| Modify | `src/automana/core/services/app_integration/mtgjson/data_loader.py` |
| Modify | `src/automana/worker/tasks/pipelines.py` |
| Modify | `src/automana/tools/tui/panels/celery.py` |
| Create | `tests/unit/core/test_storage.py` |
| Modify | `tests/unit/core/repositories/app_integration/mtgjson/test_apimtgjson_repository.py` |
| Create | `tests/unit/core/services/mtgjson/__init__.py` |
| Create | `tests/unit/core/services/mtgjson/test_data_loader.py` |
| Create | `tests/unit/worker/test_mtgjson_pipeline_wiring.py` |

---

## Task 1: Add `StorageService.build_path()`

`build_timestamped_path` already exists for timestamped files. `AllIdentifiers.json` uses a fixed filename — add the non-timestamped variant so service code has a clean API.

**Files:**
- Modify: `src/automana/core/storage.py` (after line 249, after `build_timestamped_path`)
- Create: `tests/unit/core/test_storage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/core/test_storage.py
import tempfile
from pathlib import Path

from automana.core.storage import LocalStorageBackend, StorageService


def _make_service(tmp_path: Path) -> StorageService:
    return StorageService(LocalStorageBackend(base_path=str(tmp_path)))


def test_build_path_returns_correct_absolute_path(tmp_path):
    svc = _make_service(tmp_path)
    result = svc.build_path("AllIdentifiers.json")
    assert result == tmp_path / "AllIdentifiers.json"
    assert isinstance(result, Path)


def test_build_path_is_not_timestamped(tmp_path):
    svc = _make_service(tmp_path)
    result = svc.build_path("AllIdentifiers.json")
    assert result.name == "AllIdentifiers.json"
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd /home/arthur/projects/AutoMana
PYTHONPATH=src pytest tests/unit/core/test_storage.py -v
```

Expected: `AttributeError: 'StorageService' object has no attribute 'build_path'`

- [ ] **Step 3: Add `build_path` to `StorageService`**

In `src/automana/core/storage.py`, after the `build_timestamped_path` method (line ~249), add:

```python
def build_path(self, filename: str) -> Path:
    """Return the full resolved path for a fixed-name file (no timestamp)."""
    return self.backend.resolve_path(filename)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
PYTHONPATH=src pytest tests/unit/core/test_storage.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/storage.py tests/unit/core/test_storage.py
git commit -m "feat(storage): add StorageService.build_path() for fixed-name files"
```

---

## Task 2: Add `fetch_all_identifiers_stream` to `ApimtgjsonRepository`

Mirrors `fetch_price_today_stream` exactly — thin wrapper over `stream_download`.

**Files:**
- Modify: `src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py`
- Modify: `tests/unit/core/repositories/app_integration/mtgjson/test_apimtgjson_repository.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/core/repositories/app_integration/mtgjson/test_apimtgjson_repository.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_fetch_all_identifiers_stream_calls_stream_download():
    repo = ApimtgjsonRepository(environment="test")
    dest = Path("/tmp/AllIdentifiers.json")

    with patch.object(repo, "stream_download", new_callable=AsyncMock) as mock_dl:
        mock_dl.return_value = dest
        result = await repo.fetch_all_identifiers_stream(dest)

    mock_dl.assert_called_once_with("AllIdentifiers.json", dest)
    assert result == dest
```

- [ ] **Step 2: Run test to confirm failure**

```bash
PYTHONPATH=src pytest tests/unit/core/repositories/app_integration/mtgjson/test_apimtgjson_repository.py::test_fetch_all_identifiers_stream_calls_stream_download -v
```

Expected: `AttributeError: 'ApimtgjsonRepository' object has no attribute 'fetch_all_identifiers_stream'`

- [ ] **Step 3: Add the method**

In `src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py`, inside the `# --- Streaming fetches ---` section after `fetch_all_prices_stream`:

```python
async def fetch_all_identifiers_stream(self, dest_path: Path) -> Path:
    """Stream AllIdentifiers.json to dest_path."""
    return await self.stream_download("AllIdentifiers.json", dest_path)
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/unit/core/repositories/app_integration/mtgjson/ -v
```

Expected: all pass (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/mtgjson/Apimtgjson_repository.py \
        tests/unit/core/repositories/app_integration/mtgjson/test_apimtgjson_repository.py
git commit -m "feat(mtgjson): add fetch_all_identifiers_stream to ApimtgjsonRepository"
```

---

## Task 3: Add `download_all_identifiers` service

The service downloads `AllIdentifiers.json` to a fixed path and returns `{"identifiers_filename": "AllIdentifiers.json"}` so the next chain step (`sync_uuid_mappings`) picks it up via the `run_service` context-merge.

**Files:**
- Modify: `src/automana/core/services/app_integration/mtgjson/data_loader.py`
- Create: `tests/unit/core/services/mtgjson/__init__.py`
- Create: `tests/unit/core/services/mtgjson/test_data_loader.py`

- [ ] **Step 1: Create the test package**

```bash
touch tests/unit/core/services/mtgjson/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/core/services/mtgjson/test_data_loader.py
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from automana.core.services.app_integration.mtgjson.data_loader import download_all_identifiers


@pytest.mark.asyncio
async def test_download_all_identifiers_streams_to_fixed_path():
    dest = Path("/data/automana_data/mtgjson/raw/AllIdentifiers.json")

    api_repo = MagicMock()
    api_repo.fetch_all_identifiers_stream = AsyncMock(return_value=dest)

    storage_svc = MagicMock()
    storage_svc.build_path = MagicMock(return_value=dest)

    result = await download_all_identifiers(
        mtgjson_repository=api_repo,
        storage_service=storage_svc,
    )

    storage_svc.build_path.assert_called_once_with("AllIdentifiers.json")
    api_repo.fetch_all_identifiers_stream.assert_called_once_with(dest)
    assert result == {"identifiers_filename": "AllIdentifiers.json"}
```

- [ ] **Step 3: Run test to confirm failure**

```bash
PYTHONPATH=src pytest tests/unit/core/services/mtgjson/test_data_loader.py -v
```

Expected: `ImportError` or `AttributeError` — `download_all_identifiers` does not exist yet.

- [ ] **Step 4: Add the service function**

In `src/automana/core/services/app_integration/mtgjson/data_loader.py`, after the `stage_mtgjson_data` function (the `mtgjson.data.download.today` service), add:

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
    """Stream AllIdentifiers.json from the MTGJson API to a fixed path on disk.

    Returns `identifiers_filename` so the downstream `sync_uuid_mappings` step
    picks up the refreshed file via the run_service context-merge mechanism.
    Fixed filename (no timestamp) — sync_uuid_mappings reads it by name and
    the file is always current after this step runs.
    """
    dest_path = storage_service.build_path("AllIdentifiers.json")
    logger.info("Starting MTGJson AllIdentifiers download")
    await mtgjson_repository.fetch_all_identifiers_stream(dest_path)
    logger.info("Streamed AllIdentifiers.json to disk", extra={"file": str(dest_path)})
    return {"identifiers_filename": "AllIdentifiers.json"}
```

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=src pytest tests/unit/core/services/mtgjson/test_data_loader.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/app_integration/mtgjson/data_loader.py \
        tests/unit/core/services/mtgjson/__init__.py \
        tests/unit/core/services/mtgjson/test_data_loader.py
git commit -m "feat(mtgjson): add download_all_identifiers service"
```

---

## Task 4: Reorder chain, update TUI panel, add wiring test

Reorder the `daily_mtgjson_data_pipeline` Celery chain so:
`download.all_identifiers` → `sync_uuid_mappings` → `download.today` → `stream_to_staging` → ...

Also update the TUI panel `KNOWN_TASKS` step list for `daily_mtgjson_data_pipeline` to reflect the full current chain. Then add a wiring test mirroring the mtgstock pattern to guard against future regressions.

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py`
- Modify: `src/automana/tools/tui/panels/celery.py`
- Create: `tests/unit/worker/test_mtgjson_pipeline_wiring.py`

- [ ] **Step 1: Write the failing wiring test**

```python
# tests/unit/worker/test_mtgjson_pipeline_wiring.py
"""Static structural tests for the daily_mtgjson_data_pipeline chain.

No Celery broker needed — tests inspect the KNOWN_TASKS registry and
beat_schedule config, guarding against accidental step deletion or reordering.
"""
import automana.worker.celeryconfig as celeryconfig
from automana.tools.tui.panels.celery import KNOWN_TASKS


EXPECTED_MTGJSON_STEPS = [
    "ops.pipeline_services.start_run",
    "mtgjson.data.download.all_identifiers",
    "staging.mtgjson.sync_uuid_mappings",
    "mtgjson.data.download.today",
    "staging.mtgjson.stream_to_staging",
    "staging.mtgjson.promote_to_price_observation",
    "staging.mtgjson.cleanup_raw_files",
    "ops.pipeline_services.finish_run",
]


class TestTUIPanelSteps:
    def test_mtgjson_task_listed(self):
        names = {t.name for t in KNOWN_TASKS}
        assert "daily_mtgjson_data_pipeline" in names

    def test_mtgjson_steps_match_expected(self):
        task = next(t for t in KNOWN_TASKS if t.name == "daily_mtgjson_data_pipeline")
        assert task.steps == EXPECTED_MTGJSON_STEPS

    def test_identifiers_download_before_price_download(self):
        """download.all_identifiers must run before download.today so UUID
        mappings are always current when prices are staged and promoted."""
        task = next(t for t in KNOWN_TASKS if t.name == "daily_mtgjson_data_pipeline")
        idx_ident = task.steps.index("mtgjson.data.download.all_identifiers")
        idx_sync = task.steps.index("staging.mtgjson.sync_uuid_mappings")
        idx_prices = task.steps.index("mtgjson.data.download.today")
        assert idx_ident < idx_sync < idx_prices


class TestBeatSchedule:
    def test_mtgjson_daily_entry_exists(self):
        assert "refresh-mtgjson-daily" in celeryconfig.beat_schedule

    def test_mtgjson_entry_routes_to_pipeline_task(self):
        entry = celeryconfig.beat_schedule["refresh-mtgjson-daily"]
        assert entry["task"] == (
            "automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline"
        )
```

- [ ] **Step 2: Run test to confirm failure**

```bash
PYTHONPATH=src pytest tests/unit/worker/test_mtgjson_pipeline_wiring.py -v
```

Expected: `test_mtgjson_steps_match_expected` and `test_identifiers_download_before_price_download` FAIL — the TUI panel step list is stale and doesn't include `download.all_identifiers`.

- [ ] **Step 3: Reorder the pipeline chain in `pipelines.py`**

In `src/automana/worker/tasks/pipelines.py`, inside `daily_mtgjson_data_pipeline`, replace the chain from:

```python
        run_service.s("mtgjson.data.download.today"),
        # Sync UUID mappings so the promoter proc can resolve card_uuid → card_version_id.
        # Idempotent: ON CONFLICT DO NOTHING skips duplicates on re-runs.
        run_service.s("staging.mtgjson.sync_uuid_mappings"),
        # Consumes `file_path_prices` from the download step. Streams the
```

with:

```python
        # Download fresh AllIdentifiers.json so UUID→scryfallId mappings are
        # current before prices are staged. Returns identifiers_filename for
        # sync_uuid_mappings to consume via run_service context-merge.
        run_service.s("mtgjson.data.download.all_identifiers"),
        # Idempotent: ON CONFLICT DO NOTHING skips duplicates on re-runs.
        # Must run before download.today so the promoter can resolve every
        # card_uuid staged in this run.
        run_service.s("staging.mtgjson.sync_uuid_mappings"),
        run_service.s("mtgjson.data.download.today"),
        # Consumes `file_path_prices` from the download step. Streams the
```

- [ ] **Step 4: Update the TUI panel `KNOWN_TASKS` step list**

In `src/automana/tools/tui/panels/celery.py`, find the `daily_mtgjson_data_pipeline` entry and replace its `steps` list with:

```python
        steps=[
            "ops.pipeline_services.start_run",
            "mtgjson.data.download.all_identifiers",
            "staging.mtgjson.sync_uuid_mappings",
            "mtgjson.data.download.today",
            "staging.mtgjson.stream_to_staging",
            "staging.mtgjson.promote_to_price_observation",
            "staging.mtgjson.cleanup_raw_files",
            "ops.pipeline_services.finish_run",
        ],
```

- [ ] **Step 5: Run all wiring tests**

```bash
PYTHONPATH=src pytest tests/unit/worker/test_mtgjson_pipeline_wiring.py tests/unit/worker/test_mtgstock_pipeline_wiring.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full unit test suite to confirm no regressions**

```bash
PYTHONPATH=src pytest tests/unit/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/automana/worker/tasks/pipelines.py \
        src/automana/tools/tui/panels/celery.py \
        tests/unit/worker/test_mtgjson_pipeline_wiring.py
git commit -m "feat(mtgjson): add daily AllIdentifiers.json download before price pipeline"
```

---

## Self-Review

**Spec coverage:**
- ✅ New API method (`fetch_all_identifiers_stream`) — Task 2
- ✅ `StorageService.build_path()` helper — Task 1
- ✅ `download_all_identifiers` service registered as `mtgjson.data.download.all_identifiers` — Task 3
- ✅ Chain reordered: identifiers → sync → prices — Task 4
- ✅ TUI panel updated — Task 4
- ✅ No new Beat entry (runs inside existing daily chain) — confirmed, no celeryconfig change needed

**Placeholder scan:** None found — all steps include actual code.

**Type consistency:**
- `build_path(filename: str) -> Path` — used as `storage_service.build_path("AllIdentifiers.json")` in Task 3 ✅
- `fetch_all_identifiers_stream(dest_path: Path) -> Path` — called with the `Path` returned by `build_path` ✅
- `identifiers_filename` returned as string `"AllIdentifiers.json"` — matches the existing param name in `sync_uuid_mappings` ✅
- `EXPECTED_MTGJSON_STEPS` in wiring test matches TUI panel update in Task 4 ✅
