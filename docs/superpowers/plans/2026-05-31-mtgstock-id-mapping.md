# MTGStock ID Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `card_catalog.card_external_identifier` with `mtgstock_id` rows that link each MTGStock `print_id` to its `card_version_id`, enabling price-tier queries and eliminating repeated resolution work in the staging proc.

**Architecture:** A new `MtgstockIdentifierRepository` handles all `card_catalog` reads/writes. A new `build_mtgstock_id_mapping` service reads `info.json` files from disk in parallel, resolves each `print_id` via three-step fallback (scryfall_id → tcgplayer_id → set+collector), and upserts mappings into `card_external_identifier`. A weekly Celery task wraps the service; a migration adds the `mtgstock_id` identifier type.

**Tech Stack:** Python asyncio, asyncpg, pytest + unittest.mock, PostgreSQL `ON CONFLICT DO NOTHING`

---

## File Map

| File | Change |
|------|--------|
| `src/automana/database/SQL/migrations/migration_60_mtgstock_identifier.sql` | New — insert `mtgstock_id` into `card_identifier_ref` |
| `src/automana/core/repositories/app_integration/mtg_stock/identifier_repository.py` | New — 6 query methods |
| `src/automana/core/framework/wiring.py` | Register `"mtg_stock_identifier"` DB repository |
| `src/automana/core/services/app_integration/mtg_stock/identifier_service.py` | New — `build_mtgstock_id_mapping` service |
| `src/automana/worker/tasks/pipelines.py` | Append `mtgstock_build_id_mapping` task |
| `src/automana/worker/celeryconfig.py` | Add 1 beat entry |
| `src/automana/tests/unit/repositories/mtg_stock/__init__.py` | New empty file (new package) |
| `src/automana/tests/unit/repositories/mtg_stock/test_identifier_repository.py` | New — 6 tests |
| `src/automana/tests/unit/services/mtg_stock/test_identifier_service.py` | New — 5 tests |

---

### Task 1: Migration

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_60_mtgstock_identifier.sql`

- [ ] **Step 1: Create the migration file**

Create `src/automana/database/SQL/migrations/migration_60_mtgstock_identifier.sql`:

```sql
-- Add mtgstock_id as a recognized external identifier type.
-- Enables card_external_identifier to store print_id → card_version_id links.
INSERT INTO card_catalog.card_identifier_ref (identifier_name)
VALUES ('mtgstock_id')
ON CONFLICT (identifier_name) DO NOTHING;
```

- [ ] **Step 2: Apply the migration**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -f /home/arthur/projects/AutoMana/src/automana/database/SQL/migrations/migration_60_mtgstock_identifier.sql
```

- [ ] **Step 3: Verify the row was inserted**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "SELECT card_identifier_ref_id, identifier_name FROM card_catalog.card_identifier_ref ORDER BY card_identifier_ref_id;"
```

Expected: a new row with `identifier_name = 'mtgstock_id'` appears at the end.

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_60_mtgstock_identifier.sql
git commit -m "feat(mtgstock): add mtgstock_id to card_identifier_ref (migration_60)"
```

---

### Task 2: `MtgstockIdentifierRepository` + registration

**Files:**
- Create: `src/automana/core/repositories/app_integration/mtg_stock/identifier_repository.py`
- Create: `src/automana/tests/unit/repositories/mtg_stock/__init__.py`
- Create: `src/automana/tests/unit/repositories/mtg_stock/test_identifier_repository.py`
- Modify: `src/automana/core/framework/wiring.py`

- [ ] **Step 1: Write the failing tests**

Create `src/automana/tests/unit/repositories/mtg_stock/__init__.py` (empty).

Create `src/automana/tests/unit/repositories/mtg_stock/test_identifier_repository.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_repo():
    from automana.core.repositories.app_integration.mtg_stock.identifier_repository import (
        MtgstockIdentifierRepository,
    )
    repo = MtgstockIdentifierRepository.__new__(MtgstockIdentifierRepository)
    repo.execute_query = AsyncMock()
    repo.execute_command = AsyncMock()
    repo.execute_many = AsyncMock()
    repo.execute_fetchval = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_get_mtgstock_ref_id_returns_int():
    repo = _make_repo()
    repo.execute_fetchval.return_value = 8
    result = await repo.get_mtgstock_ref_id()
    assert result == 8
    repo.execute_fetchval.assert_awaited_once()
    assert "mtgstock_id" in repo.execute_fetchval.call_args[0][0]


@pytest.mark.asyncio
async def test_get_existing_mapped_print_ids_returns_set():
    repo = _make_repo()
    repo.execute_fetchval.return_value = 8
    repo.execute_query.return_value = [{"value": 1001}, {"value": 2002}]
    result = await repo.get_existing_mapped_print_ids()
    assert result == {1001, 2002}


@pytest.mark.asyncio
async def test_resolve_by_scryfall_returns_mapping():
    repo = _make_repo()
    repo.execute_query.return_value = [
        {"scryfall_id": "abc-123", "card_version_id": "uuid-1"},
    ]
    result = await repo.resolve_by_scryfall(["abc-123", "def-456"])
    assert result == {"abc-123": "uuid-1"}
    assert "scryfall_id" in repo.execute_query.call_args[0][0]


@pytest.mark.asyncio
async def test_resolve_by_tcgplayer_returns_mapping():
    repo = _make_repo()
    repo.execute_query.return_value = [
        {"tcg_id": "576888", "card_version_id": "uuid-2"},
    ]
    result = await repo.resolve_by_tcgplayer(["576888"])
    assert result == {"576888": "uuid-2"}
    assert "tcgplayer_id" in repo.execute_query.call_args[0][0]


@pytest.mark.asyncio
async def test_resolve_by_set_collector_returns_mapping():
    repo = _make_repo()
    repo.execute_query.return_value = [
        {"set_code": "dsk", "collector_number": "232", "card_version_id": "uuid-3"},
    ]
    result = await repo.resolve_by_set_collector([("DSK", "232")])
    assert ("DSK", "232") in result
    assert result[("DSK", "232")] == "uuid-3"


@pytest.mark.asyncio
async def test_upsert_mtgstock_id_mappings_calls_execute_many():
    repo = _make_repo()
    repo.execute_fetchval.return_value = 8
    mappings = [
        {"card_version_id": "uuid-1", "print_id": 1001},
        {"card_version_id": "uuid-2", "print_id": 1002},
    ]
    await repo.upsert_mtgstock_id_mappings(mappings)
    repo.execute_many.assert_awaited_once()
    rows = repo.execute_many.call_args[0][1]
    assert len(rows) == 2
    assert rows[0] == ("uuid-1", 8, "1001")
    assert rows[1] == ("uuid-2", 8, "1002")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/arthur/projects/AutoMana/src && python -m pytest automana/tests/unit/repositories/mtg_stock/test_identifier_repository.py -v
```

Expected: `ImportError` — `identifier_repository` doesn't exist yet.

- [ ] **Step 3: Implement `MtgstockIdentifierRepository`**

Create `src/automana/core/repositories/app_integration/mtg_stock/identifier_repository.py`:

```python
import logging
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)


class MtgstockIdentifierRepository(AbstractRepository):

    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "MtgstockIdentifierRepository"

    async def get_mtgstock_ref_id(self) -> int:
        return await self.execute_fetchval(
            "SELECT card_identifier_ref_id FROM card_catalog.card_identifier_ref "
            "WHERE identifier_name = 'mtgstock_id'"
        )

    async def get_existing_mapped_print_ids(self) -> set[int]:
        ref_id = await self.get_mtgstock_ref_id()
        rows = await self.execute_query(
            "SELECT value::int FROM card_catalog.card_external_identifier "
            "WHERE card_identifier_ref_id = $1",
            (ref_id,),
        )
        return {r["value"] for r in rows}

    async def resolve_by_scryfall(self, scryfall_ids: list[str]) -> dict[str, str]:
        """Return {scryfall_id: card_version_id} for matching IDs."""
        if not scryfall_ids:
            return {}
        rows = await self.execute_query(
            """
            SELECT cei.value AS scryfall_id, cei.card_version_id::text
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name = 'scryfall_id'
              AND cei.value = ANY($1)
            """,
            (scryfall_ids,),
        )
        return {r["scryfall_id"]: r["card_version_id"] for r in rows}

    async def resolve_by_tcgplayer(self, tcg_ids: list[str]) -> dict[str, str]:
        """Return {tcgplayer_id: card_version_id} for matching IDs."""
        if not tcg_ids:
            return {}
        rows = await self.execute_query(
            """
            SELECT cei.value AS tcg_id, cei.card_version_id::text
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name = 'tcgplayer_id'
              AND cei.value = ANY($1)
            """,
            (tcg_ids,),
        )
        return {r["tcg_id"]: r["card_version_id"] for r in rows}

    async def resolve_by_set_collector(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], str]:
        """Return {(set_abbr, collector_number): card_version_id} for matching pairs."""
        if not pairs:
            return {}
        set_abbrs = list({p[0].lower() for p in pairs})
        rows = await self.execute_query(
            """
            SELECT lower(s.set_code) AS set_code, cv.collector_number::text, cv.card_version_id::text
            FROM card_catalog.card_version cv
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            WHERE lower(s.set_code) = ANY($1)
            """,
            (set_abbrs,),
        )
        lookup = {
            (r["set_code"], r["collector_number"]): r["card_version_id"] for r in rows
        }
        return {
            (abbr, num): lookup[(abbr.lower(), str(num))]
            for abbr, num in pairs
            if (abbr.lower(), str(num)) in lookup
        }

    async def upsert_mtgstock_id_mappings(self, mappings: list[dict]) -> int:
        """Insert {card_version_id, print_id} rows. ON CONFLICT DO NOTHING."""
        if not mappings:
            return 0
        ref_id = await self.get_mtgstock_ref_id()
        rows = [(m["card_version_id"], ref_id, str(m["print_id"])) for m in mappings]
        await self.execute_many(
            """
            INSERT INTO card_catalog.card_external_identifier
                (card_version_id, card_identifier_ref_id, value)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
        return len(rows)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/arthur/projects/AutoMana/src && python -m pytest automana/tests/unit/repositories/mtg_stock/test_identifier_repository.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Register in wiring.py**

In `src/automana/core/framework/wiring.py`, after the `"price"` registration line, add:

```python
ServiceRegistry.register_db_repository(
    "mtg_stock_identifier",
    "automana.core.repositories.app_integration.mtg_stock.identifier_repository",
    "MtgstockIdentifierRepository",
)
```

- [ ] **Step 6: Verify registration**

```bash
cd /home/arthur/projects/AutoMana/src && python -c "
from automana.core.framework.wiring import *
from automana.core.framework.registry import ServiceRegistry
info = ServiceRegistry.get_db_repository('mtg_stock_identifier')
print('registered:', info)
"
```

Expected: prints the module path and class name tuple. No import error.

- [ ] **Step 7: Commit**

```bash
git add \
  src/automana/core/repositories/app_integration/mtg_stock/identifier_repository.py \
  src/automana/core/framework/wiring.py \
  src/automana/tests/unit/repositories/mtg_stock/__init__.py \
  src/automana/tests/unit/repositories/mtg_stock/test_identifier_repository.py
git commit -m "feat(mtgstock): add MtgstockIdentifierRepository for print_id → card_version_id mapping"
```

---

### Task 3: `build_mtgstock_id_mapping` service

**Files:**
- Create: `src/automana/core/services/app_integration/mtg_stock/identifier_service.py`
- Create/modify: `src/automana/tests/unit/services/mtg_stock/test_identifier_service.py`

- [ ] **Step 1: Write the failing tests**

Create `src/automana/tests/unit/services/mtg_stock/test_identifier_service.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


def _make_identifier_repo(
    existing=None,
    scryfall_map=None,
    tcg_map=None,
    set_col_map=None,
):
    repo = MagicMock()
    repo.get_existing_mapped_print_ids = AsyncMock(return_value=set(existing or []))
    repo.resolve_by_scryfall = AsyncMock(return_value=scryfall_map or {})
    repo.resolve_by_tcgplayer = AsyncMock(return_value=tcg_map or {})
    repo.resolve_by_set_collector = AsyncMock(return_value=set_col_map or {})
    repo.upsert_mtgstock_id_mappings = AsyncMock(return_value=0)
    return repo


def _write_ids(folder: Path, ids: list[int]):
    (folder / "existing_ids.json").write_text(json.dumps(ids))


def _write_info(folder: Path, print_id: int, scryfall_id=None, tcg_id=None,
                set_abbr=None, collector=None):
    d = folder / str(print_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "info.json").write_text(json.dumps({
        "id": print_id,
        "scryfallId": scryfall_id,
        "tcg_id": tcg_id,
        "collector_number": collector,
        "card_set": {"abbreviation": set_abbr} if set_abbr else None,
    }))


@pytest.mark.asyncio
async def test_build_mapping_skips_existing_print_ids(tmp_path):
    """IDs already in card_external_identifier are not re-processed."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001, 1002, 1003])
    repo = _make_identifier_repo(existing={1001, 1002, 1003})
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()

    result = await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
    )

    assert result["skipped_existing"] == 3
    assert result["mapped"] == 0
    repo.upsert_mtgstock_id_mappings.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_mapping_resolves_by_scryfall_first(tmp_path):
    """scryfall_id match is used before tcgplayer or set+collector fallbacks."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001])
    _write_info(tmp_path, 1001, scryfall_id="abc-111", tcg_id=999)

    repo = _make_identifier_repo(
        scryfall_map={"abc-111": "uuid-cv-1"},
    )
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()
    repo.upsert_mtgstock_id_mappings = AsyncMock(return_value=1)

    await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
        batch_size=10,
    )

    mappings_passed = repo.upsert_mtgstock_id_mappings.call_args[0][0]
    assert any(m["print_id"] == 1001 and m["card_version_id"] == "uuid-cv-1"
               for m in mappings_passed)


@pytest.mark.asyncio
async def test_build_mapping_falls_back_to_tcgplayer(tmp_path):
    """When scryfall_id yields no match, tcgplayer_id is tried."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001])
    _write_info(tmp_path, 1001, scryfall_id="abc-111", tcg_id=576888)

    repo = _make_identifier_repo(
        scryfall_map={},
        tcg_map={"576888": "uuid-cv-2"},
    )
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()
    repo.upsert_mtgstock_id_mappings = AsyncMock(return_value=1)

    await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
        batch_size=10,
    )

    mappings_passed = repo.upsert_mtgstock_id_mappings.call_args[0][0]
    assert any(m["print_id"] == 1001 and m["card_version_id"] == "uuid-cv-2"
               for m in mappings_passed)


@pytest.mark.asyncio
async def test_build_mapping_handles_missing_info_json(tmp_path):
    """Print IDs with no info.json on disk are counted as unresolved, not crashed."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001])
    # Intentionally do NOT create info.json for 1001

    repo = _make_identifier_repo()
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()

    result = await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
    )

    assert result["unresolved"] == 1
    assert result["mapped"] == 0


@pytest.mark.asyncio
async def test_build_mapping_returns_counts(tmp_path):
    """Return dict has mapped, skipped_existing, unresolved keys with correct values."""
    from automana.core.services.app_integration.mtg_stock.identifier_service import (
        build_mtgstock_id_mapping,
    )
    _write_ids(tmp_path, [1001, 1002])
    # 1002 already mapped, 1001 has no info.json → unresolved

    repo = _make_identifier_repo(existing={1002})
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()

    result = await build_mtgstock_id_mapping(
        mtg_stock_identifier_repository=repo,
        destination_folder=str(tmp_path),
        ingestion_run_id=1,
        ops_repository=ops_repo,
    )

    assert result["skipped_existing"] == 1
    assert result["unresolved"] == 1
    assert result["mapped"] == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/arthur/projects/AutoMana/src && python -m pytest automana/tests/unit/services/mtg_stock/test_identifier_service.py -v
```

Expected: `ImportError` — `identifier_service` doesn't exist yet.

- [ ] **Step 3: Implement `build_mtgstock_id_mapping` service**

Create `src/automana/core/services/app_integration/mtg_stock/identifier_service.py`:

```python
import asyncio
import json
import logging
from pathlib import Path

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.app_integration.mtg_stock.identifier_repository import (
    MtgstockIdentifierRepository,
)
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.services.ops.pipeline_services import track_step

logger = logging.getLogger(__name__)

_SEM = asyncio.Semaphore(50)


@ServiceRegistry.register(
    "mtg_stock.identifier.build_mapping",
    db_repositories=["mtg_stock_identifier", "ops"],
)
async def build_mtgstock_id_mapping(
    mtg_stock_identifier_repository: MtgstockIdentifierRepository,
    destination_folder: str,
    ingestion_run_id: int,
    batch_size: int = 500,
    ops_repository: OpsRepository | None = None,
) -> dict:
    """Resolve print_id → card_version_id from info.json files and upsert into card_external_identifier."""
    ids_path = Path(destination_folder) / "existing_ids.json"
    all_ids: list[int] = json.loads(ids_path.read_text())

    existing = await mtg_stock_identifier_repository.get_existing_mapped_print_ids()
    unmapped = [i for i in all_ids if i not in existing]

    logger.info(
        "MTGStock ID mapping starting",
        extra={"total": len(all_ids), "already_mapped": len(existing), "to_process": len(unmapped)},
    )

    mapped = 0
    unresolved = 0

    async def _read_info(print_id: int) -> dict | None:
        info_path = Path(destination_folder) / str(print_id) / "info.json"
        if not info_path.exists():
            return None
        async with _SEM:
            return await asyncio.to_thread(
                lambda: json.loads(info_path.read_text())
            )

    async with track_step(ops_repository, ingestion_run_id, "build_mtgstock_id_mapping"):
        for batch_start in range(0, len(unmapped), batch_size):
            batch_ids = unmapped[batch_start: batch_start + batch_size]
            info_results = await asyncio.gather(*[_read_info(pid) for pid in batch_ids])

            id_data = [
                {
                    "print_id": pid,
                    "scryfall_id": info.get("scryfallId"),
                    "tcg_id": str(info["tcg_id"]) if info.get("tcg_id") else None,
                    "set_abbr": (info.get("card_set") or {}).get("abbreviation"),
                    "collector_number": str(info.get("collector_number", "")),
                }
                for pid, info in zip(batch_ids, info_results)
                if info is not None
            ]

            resolved: dict[int, str] = {}

            # Step 1: scryfall_id
            scryfall_lookup = {d["scryfall_id"]: d["print_id"] for d in id_data if d.get("scryfall_id")}
            if scryfall_lookup:
                matches = await mtg_stock_identifier_repository.resolve_by_scryfall(
                    list(scryfall_lookup)
                )
                for sid, cv_id in matches.items():
                    resolved[scryfall_lookup[sid]] = cv_id

            # Step 2: tcgplayer_id
            remaining = [d for d in id_data if d["print_id"] not in resolved and d.get("tcg_id")]
            if remaining:
                tcg_lookup = {d["tcg_id"]: d["print_id"] for d in remaining}
                matches = await mtg_stock_identifier_repository.resolve_by_tcgplayer(list(tcg_lookup))
                for tid, cv_id in matches.items():
                    resolved[tcg_lookup[tid]] = cv_id

            # Step 3: set_abbr + collector_number
            remaining = [
                d for d in id_data
                if d["print_id"] not in resolved and d.get("set_abbr") and d.get("collector_number")
            ]
            if remaining:
                pair_to_pid = {(d["set_abbr"], d["collector_number"]): d["print_id"] for d in remaining}
                matches = await mtg_stock_identifier_repository.resolve_by_set_collector(
                    list(pair_to_pid)
                )
                for pair, cv_id in matches.items():
                    pid = pair_to_pid.get(pair)
                    if pid and pid not in resolved:
                        resolved[pid] = cv_id

            batch_unresolved = len(batch_ids) - len(resolved)
            unresolved += batch_unresolved

            if resolved:
                mappings = [
                    {"card_version_id": cv_id, "print_id": pid}
                    for pid, cv_id in resolved.items()
                ]
                inserted = await mtg_stock_identifier_repository.upsert_mtgstock_id_mappings(mappings)
                mapped += inserted

            logger.info(
                "MTGStock ID mapping batch complete",
                extra={
                    "batch_start": batch_start,
                    "resolved": len(resolved),
                    "unresolved": batch_unresolved,
                },
            )

    return {"mapped": mapped, "skipped_existing": len(existing), "unresolved": unresolved}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/arthur/projects/AutoMana/src && python -m pytest automana/tests/unit/services/mtg_stock/test_identifier_service.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add \
  src/automana/core/services/app_integration/mtg_stock/identifier_service.py \
  src/automana/tests/unit/services/mtg_stock/test_identifier_service.py
git commit -m "feat(mtgstock): add build_mtgstock_id_mapping service"
```

---

### Task 4: Celery task + beat entry + idempotency coverage

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py`
- Modify: `src/automana/worker/celeryconfig.py`
- Modify: `src/automana/tests/unit/tasks/test_pipeline_idempotency_guard.py`

- [ ] **Step 1: Append task to `pipelines.py`**

The task must import the identifier service so it registers with ServiceRegistry. Add this import near the top of `src/automana/worker/tasks/pipelines.py` (with the other service imports at the end of the import block):

```python
from automana.core.services.app_integration.mtg_stock import identifier_service  # noqa: F401 — registers service
```

Then append to the end of `src/automana/worker/tasks/pipelines.py`:

```python
@shared_task(name="automana.worker.tasks.pipelines.mtgstock_build_id_mapping", bind=True)
def mtgstock_build_id_mapping(self):
    """Weekly: resolve print_id → card_version_id and populate card_external_identifier."""
    set_task_id(self.request.id)
    today = datetime.utcnow().date().isoformat()
    run_key = f"mtgStock_id_mapping:{today}"
    logger.info("Starting MTGStock ID mapping build", extra={"run_key": run_key})

    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgstock_build_id_mapping",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("mtg_stock.identifier.build_mapping",
                      destination_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=500),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id
```

- [ ] **Step 2: Add beat schedule entry**

In `src/automana/worker/celeryconfig.py`, append inside `beat_schedule` before the closing `}`:

```python
    # Weekly mtgstock_id → card_version_id mapping build.
    # Runs at 02:00 AEST Sunday, after discover-new-ids (01:00) so new IDs are mapped same run.
    "mtgstock-build-id-mapping": {
        "task": "automana.worker.tasks.pipelines.mtgstock_build_id_mapping",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 02:00 AEST
    },
```

- [ ] **Step 3: Extend idempotency guard test**

In `src/automana/tests/unit/tasks/test_pipeline_idempotency_guard.py`, add to `PIPELINES`:

```python
    ("automana.worker.tasks.pipelines.mtgstock_build_id_mapping", "mtgstock_build_id_mapping"),
```

- [ ] **Step 4: Run idempotency guard tests**

```bash
cd /home/arthur/projects/AutoMana/src && python -m pytest automana/tests/unit/tasks/test_pipeline_idempotency_guard.py -v
```

Expected: all cases pass. The new task adds 2 more parametrized cases.

- [ ] **Step 5: Verify task name is registered**

```bash
cd /home/arthur/projects/AutoMana/src && python -c "
from automana.worker.tasks.pipelines import mtgstock_build_id_mapping
print(mtgstock_build_id_mapping.name)
"
```

Expected: `automana.worker.tasks.pipelines.mtgstock_build_id_mapping`

- [ ] **Step 6: Commit**

```bash
git add \
  src/automana/worker/tasks/pipelines.py \
  src/automana/worker/celeryconfig.py \
  src/automana/tests/unit/tasks/test_pipeline_idempotency_guard.py
git commit -m "feat(mtgstock): add mtgstock_build_id_mapping task and Sunday beat entry"
```

---

### Task 5: Full test run + live smoke test

- [ ] **Step 1: Run all unit tests**

```bash
cd /home/arthur/projects/AutoMana/src && python -m pytest automana/tests/unit/tasks/ automana/tests/unit/services/ automana/tests/unit/repositories/ -v --tb=short 2>&1 | tail -20
```

Expected: no new failures vs the baseline (1 pre-existing failure in `test_fulfillment_service_augmented.py` is expected).

- [ ] **Step 2: Restart worker and verify task registered**

```bash
docker restart automana-celery-dev
sleep 15
docker exec automana-celery-dev celery -A automana.worker.main inspect registered 2>/dev/null | grep mtgstock_build
```

Expected: `automana.worker.tasks.pipelines.mtgstock_build_id_mapping`

- [ ] **Step 3: Fire the task manually with a small batch**

```bash
docker exec automana-celery-dev celery -A automana.worker.main call \
  automana.worker.tasks.pipelines.mtgstock_build_id_mapping 2>/dev/null
```

- [ ] **Step 4: Poll ops until terminal status**

```bash
until docker exec automana-postgres-dev psql -U automana_admin automana -tAc \
  "SELECT status FROM ops.ingestion_runs WHERE run_key LIKE 'mtgStock_id_mapping:%' ORDER BY id DESC LIMIT 1" \
  | grep -qE "success|failed"; do sleep 5; done
docker exec automana-postgres-dev psql -U automana_admin automana -c \
  "SELECT run_key, status, notes FROM ops.ingestion_runs WHERE run_key LIKE 'mtgStock_id_mapping:%' ORDER BY id DESC LIMIT 1;"
```

Expected: `status = success`

- [ ] **Step 5: Verify rows were inserted**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT COUNT(*) AS mapped_count
FROM card_catalog.card_external_identifier cei
JOIN card_catalog.card_identifier_ref cir ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
WHERE cir.identifier_name = 'mtgstock_id';"
```

Expected: a positive count (target ~85K–90K of 95,615 total print IDs).

- [ ] **Step 6: Invoke finishing-a-development-branch skill to open PR**

Use `superpowers:finishing-a-development-branch` to open the PR against `dev`.
