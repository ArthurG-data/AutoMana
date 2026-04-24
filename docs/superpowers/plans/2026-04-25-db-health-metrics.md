# Database Health Metrics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two new metric families (`card_catalog.*` and `pricing.*`, 15 metrics total) that surface data-shape drift like the 113k-missing-scryfall-id incident, exposed via two new runner services auto-discovered by the `pipeline-health-check` skill.

**Architecture:** Follows the existing `MetricRegistry` pattern documented in `docs/METRICS_REGISTRY.md` exactly: per-family package under `core/metrics/<family>/`, runner service under `core/services/ops/<family>_report.py`. Repository methods are read-only SELECT-only and added to the existing `CardReferenceRepository`, `PriceRepository`, `OpsRepository`. A shared `_metric_runner.py` helper is extracted because three runners (mtgstock + the two new ones) is the threshold where DRY pays off.

**Tech Stack:** Python 3.11+ async, asyncpg, pytest + AsyncMock, Celery beat, FastAPI (untouched), PostgreSQL + TimescaleDB (untouched).

**Spec:** `docs/superpowers/specs/2026-04-25-db-health-metrics-design.md`

---

## Conventions used in this plan

- Every repository method uses `await self.execute_query(query, (arg1, arg2))` — args passed as a single **tuple**, not unpacked. (Match `OpsRepository.get_latest_run_id` lines 443–453.)
- Returned rows behave like dicts (`row["col"]`).
- Test files mirror src layout: `tests/unit/core/metrics/<family>/test_<module>.py`, `tests/unit/core/services/ops/test_<family>_report.py`.
- Tests are marked `pytestmark = pytest.mark.unit` (match `test_mtgstock_report.py`).
- Commits are `feat(metrics):` / `feat(repo):` / `refactor(metrics):` style — match recent commit history.
- All test commands assume cwd = repo root, run `pytest` directly (configured in `pyproject.toml`).

---

## Task 1: `CardReferenceRepository.fetch_identifier_coverage_pct`

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py` (append method to `CardReferenceRepository`)
- Test: `tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py` (create new file)

- [ ] **Step 1.1: Write the failing test**

```python
# tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py
"""Tests for the metric-support read methods added to CardReferenceRepository.

These methods feed the card_catalog.* metric family — they are read-only and
return small scalar / dict shapes specifically for the registry runner.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.repositories.card_catalog.card_repository import (
    CardReferenceRepository,
)

pytestmark = pytest.mark.unit


def _make_repo(rows):
    """Build a CardReferenceRepository with a mocked execute_query that
    returns the provided rows on the next call."""
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_fetch_identifier_coverage_pct_returns_pct_and_counts():
    repo = _make_repo([{"covered": 95, "total": 100, "pct": 95.0}])
    out = await repo.fetch_identifier_coverage_pct("scryfall_id")
    assert out == {"covered": 95, "total": 100, "pct": 95.0}
    repo.execute_query.assert_awaited_once()
    args = repo.execute_query.await_args.args
    assert args[1] == ("scryfall_id",)


@pytest.mark.asyncio
async def test_fetch_identifier_coverage_pct_zero_total_returns_none_pct():
    repo = _make_repo([{"covered": 0, "total": 0, "pct": None}])
    out = await repo.fetch_identifier_coverage_pct("scryfall_id")
    assert out == {"covered": 0, "total": 0, "pct": None}


@pytest.mark.asyncio
async def test_fetch_identifier_coverage_pct_no_rows_returns_none():
    repo = _make_repo([])
    out = await repo.fetch_identifier_coverage_pct("scryfall_id")
    assert out is None
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `pytest tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py -v`
Expected: FAIL — `AttributeError: 'CardReferenceRepository' object has no attribute 'fetch_identifier_coverage_pct'`

- [ ] **Step 1.3: Implement the method**

Append to `src/automana/core/repositories/card_catalog/card_repository.py` inside `class CardReferenceRepository`:

```python
    async def fetch_identifier_coverage_pct(self, identifier_name: str) -> dict | None:
        """Return per-identifier coverage stats for the card_catalog.identifier_coverage.* metrics.

        Returns ``{'covered': int, 'total': int, 'pct': float|None}``. ``pct`` is
        NULL when ``total`` is 0 — the metric layer treats NULL as Severity.WARN
        rather than silently passing.
        """
        query = """
        WITH totals AS (
            SELECT COUNT(*)::int AS total FROM card_catalog.card_version
        ),
        covered AS (
            SELECT COUNT(DISTINCT cei.card_version_id)::int AS covered
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name = $1
        )
        SELECT
            covered,
            total,
            CASE WHEN total = 0 THEN NULL
                 ELSE ROUND(100.0 * covered / total, 2)::float
            END AS pct
        FROM totals, covered
        """
        rows = await self.execute_query(query, (identifier_name,))
        return dict(rows[0]) if rows else None
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `pytest tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py -v`
Expected: 3 passing.

- [ ] **Step 1.5: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py \
        tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py
git commit -m "feat(repo): CardReferenceRepository.fetch_identifier_coverage_pct"
```

---

## Task 2: Card-catalog identifier metrics (6 metrics)

**Files:**
- Create: `src/automana/core/metrics/card_catalog/__init__.py`
- Create: `src/automana/core/metrics/card_catalog/identifier_metrics.py`
- Test: `tests/unit/core/metrics/card_catalog/__init__.py` (empty)
- Test: `tests/unit/core/metrics/card_catalog/test_identifier_metrics.py`

- [ ] **Step 2.1: Write the failing tests**

```python
# tests/unit/core/metrics/card_catalog/test_identifier_metrics.py
"""Tests for card_catalog.identifier_coverage.* metrics.

Each metric is a thin wrapper over CardReferenceRepository.fetch_identifier_coverage_pct
(or .fetch_identifier_value_count for the informational ones). Tests mock
the repository and assert the returned MetricResult shape — including the
details dict — and the threshold-evaluated severity.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
# Importing the package triggers registration of all card_catalog.* metrics.
import automana.core.metrics.card_catalog  # noqa: F401
from automana.core.metrics.card_catalog.identifier_metrics import (
    scryfall_id_coverage,
    oracle_id_coverage,
    tcgplayer_id_coverage,
    cardmarket_id_coverage,
    multiverse_id_count,
    tcgplayer_etched_id_count,
)

pytestmark = pytest.mark.unit


def _repo(coverage=None, value_count=None):
    repo = AsyncMock()
    repo.fetch_identifier_coverage_pct.return_value = coverage
    repo.fetch_identifier_value_count.return_value = value_count
    return repo


@pytest.mark.asyncio
async def test_scryfall_id_coverage_healthy_value_returns_ok():
    repo = _repo(coverage={"covered": 99500, "total": 100000, "pct": 99.5})
    result = await scryfall_id_coverage(card_repository=repo)
    assert result.row_count == 99.5
    assert result.details == {"identifier_name": "scryfall_id", "covered": 99500, "total": 100000}
    cfg = MetricRegistry.get("card_catalog.identifier_coverage.scryfall_id")
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.OK


@pytest.mark.asyncio
async def test_scryfall_id_coverage_below_warn_returns_warn():
    repo = _repo(coverage={"covered": 96000, "total": 100000, "pct": 96.0})
    result = await scryfall_id_coverage(card_repository=repo)
    cfg = MetricRegistry.get("card_catalog.identifier_coverage.scryfall_id")
    # warn=99 lower_is_worse → 96 ≤ 99 triggers WARN (and 96 > error=95 so not ERROR)
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.WARN


@pytest.mark.asyncio
async def test_scryfall_id_coverage_below_error_returns_error():
    repo = _repo(coverage={"covered": 80000, "total": 100000, "pct": 80.0})
    result = await scryfall_id_coverage(card_repository=repo)
    cfg = MetricRegistry.get("card_catalog.identifier_coverage.scryfall_id")
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.ERROR


@pytest.mark.asyncio
async def test_scryfall_id_coverage_zero_total_returns_none_warns():
    repo = _repo(coverage={"covered": 0, "total": 0, "pct": None})
    result = await scryfall_id_coverage(card_repository=repo)
    assert result.row_count is None
    cfg = MetricRegistry.get("card_catalog.identifier_coverage.scryfall_id")
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.WARN


@pytest.mark.asyncio
async def test_scryfall_id_coverage_repo_returns_none_returns_none():
    repo = _repo(coverage=None)
    result = await scryfall_id_coverage(card_repository=repo)
    assert result.row_count is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metric_fn,name",
    [
        (oracle_id_coverage, "oracle_id"),
        (tcgplayer_id_coverage, "tcgplayer_id"),
        (cardmarket_id_coverage, "cardmarket_id"),
    ],
)
async def test_other_pct_coverage_metrics_pass_correct_identifier_name(metric_fn, name):
    repo = _repo(coverage={"covered": 50, "total": 100, "pct": 50.0})
    await metric_fn(card_repository=repo)
    repo.fetch_identifier_coverage_pct.assert_awaited_once_with(name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metric_fn,name,path",
    [
        (multiverse_id_count, "multiverse_id", "card_catalog.identifier_coverage.multiverse_id"),
        (tcgplayer_etched_id_count, "tcgplayer_etched_id", "card_catalog.identifier_coverage.tcgplayer_etched_id"),
    ],
)
async def test_informational_count_metrics_return_count_no_threshold(metric_fn, name, path):
    repo = _repo(value_count=42)
    result = await metric_fn(card_repository=repo)
    assert result.row_count == 42
    assert result.details == {"identifier_name": name}
    repo.fetch_identifier_value_count.assert_awaited_once_with(name)
    cfg = MetricRegistry.get(path)
    assert cfg.severity is None
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.OK
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `pytest tests/unit/core/metrics/card_catalog/test_identifier_metrics.py -v`
Expected: ImportError — `automana.core.metrics.card_catalog` does not exist yet.

- [ ] **Step 2.3: Add the second repository method**

Append to `src/automana/core/repositories/card_catalog/card_repository.py` inside `class CardReferenceRepository`:

```python
    async def fetch_identifier_value_count(self, identifier_name: str) -> int:
        """COUNT of card_version rows that have at least one row for ``identifier_name``.

        Used by the informational metrics (multiverse_id, tcgplayer_etched_id)
        which track raw counts rather than coverage percentages.
        """
        query = """
        SELECT COUNT(DISTINCT cei.card_version_id)::int AS n
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
        WHERE cir.identifier_name = $1
        """
        rows = await self.execute_query(query, (identifier_name,))
        return rows[0]["n"] if rows else 0
```

- [ ] **Step 2.4: Create the package and the metric module**

Create `src/automana/core/metrics/card_catalog/__init__.py`:

```python
from automana.core.metrics.card_catalog import identifier_metrics  # noqa: F401
```

Create `src/automana/core/metrics/card_catalog/identifier_metrics.py`:

```python
"""card_catalog.identifier_coverage.* metrics.

Coverage = % of card_version rows that have at least one row in
card_external_identifier for the given identifier_name. Per-source thresholds
reflect that scryfall_id and oracle_id should be near-100%, tcgplayer_id and
cardmarket_id naturally lower, and multiverse_id / tcgplayer_etched_id are
informational only (low coverage is expected).
"""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository


async def _coverage(card_repository: CardReferenceRepository, name: str) -> MetricResult:
    out = await card_repository.fetch_identifier_coverage_pct(name)
    if out is None:
        return MetricResult(row_count=None, details={"identifier_name": name})
    return MetricResult(
        row_count=out["pct"],
        details={"identifier_name": name, "covered": out["covered"], "total": out["total"]},
    )


async def _count(card_repository: CardReferenceRepository, name: str) -> MetricResult:
    n = await card_repository.fetch_identifier_value_count(name)
    return MetricResult(row_count=n, details={"identifier_name": name})


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.scryfall_id",
    category="health",
    description="% of card_version rows that have a scryfall_id external identifier.",
    severity=Threshold(warn=99, error=95, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def scryfall_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    return await _coverage(card_repository, "scryfall_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.oracle_id",
    category="health",
    description="% of card_version rows that have an oracle_id external identifier.",
    severity=Threshold(warn=99, error=95, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def oracle_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    return await _coverage(card_repository, "oracle_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.tcgplayer_id",
    category="health",
    description="% of card_version rows that have a tcgplayer_id external identifier.",
    severity=Threshold(warn=80, error=60, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def tcgplayer_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    return await _coverage(card_repository, "tcgplayer_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.cardmarket_id",
    category="health",
    description="% of card_version rows that have a cardmarket_id external identifier.",
    severity=Threshold(warn=70, error=50, direction="lower_is_worse"),
    db_repositories=["card"],
)
async def cardmarket_id_coverage(card_repository: CardReferenceRepository) -> MetricResult:
    return await _coverage(card_repository, "cardmarket_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.multiverse_id",
    category="volume",
    description="Count of card_version rows with a (deprecated) multiverse_id identifier.",
    severity=None,
    db_repositories=["card"],
)
async def multiverse_id_count(card_repository: CardReferenceRepository) -> MetricResult:
    return await _count(card_repository, "multiverse_id")


@MetricRegistry.register(
    path="card_catalog.identifier_coverage.tcgplayer_etched_id",
    category="volume",
    description="Count of card_version rows with a tcgplayer_etched_id identifier.",
    severity=None,
    db_repositories=["card"],
)
async def tcgplayer_etched_id_count(card_repository: CardReferenceRepository) -> MetricResult:
    return await _count(card_repository, "tcgplayer_etched_id")
```

- [ ] **Step 2.5: Run tests to verify they pass**

Run: `pytest tests/unit/core/metrics/card_catalog/test_identifier_metrics.py -v`
Expected: all parametrized tests passing (~10 cases).

- [ ] **Step 2.6: Commit**

```bash
git add src/automana/core/metrics/card_catalog/ \
        tests/unit/core/metrics/card_catalog/ \
        src/automana/core/repositories/card_catalog/card_repository.py
git commit -m "feat(metrics): card_catalog.identifier_coverage.* metrics (6 metrics)"
```

---

## Task 3: Card-catalog non-identifier metrics (orphan + collision)

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py` (two more methods)
- Modify: `tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py`
- Create: `src/automana/core/metrics/card_catalog/catalog_metrics.py`
- Modify: `src/automana/core/metrics/card_catalog/__init__.py`
- Test: `tests/unit/core/metrics/card_catalog/test_catalog_metrics.py`

- [ ] **Step 3.1: Write the failing repository tests**

Append to `tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py`:

```python
@pytest.mark.asyncio
async def test_fetch_orphan_unique_cards_count_returns_int():
    repo = _make_repo([{"n": 7}])
    n = await repo.fetch_orphan_unique_cards_count()
    assert n == 7


@pytest.mark.asyncio
async def test_fetch_orphan_unique_cards_count_no_rows_returns_zero():
    repo = _make_repo([])
    assert await repo.fetch_orphan_unique_cards_count() == 0


@pytest.mark.asyncio
async def test_fetch_external_id_value_collisions_returns_int():
    repo = _make_repo([{"n": 0}])
    assert await repo.fetch_external_id_value_collisions() == 0


@pytest.mark.asyncio
async def test_fetch_external_id_value_collisions_no_rows_returns_zero():
    repo = _make_repo([])
    assert await repo.fetch_external_id_value_collisions() == 0
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `pytest tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py -v`
Expected: 4 new tests fail with `AttributeError`.

- [ ] **Step 3.3: Implement the two repository methods**

Append to `class CardReferenceRepository`:

```python
    async def fetch_orphan_unique_cards_count(self) -> int:
        """COUNT of unique_cards_ref rows with zero card_version children.

        Small counts are benign (tokens / emblems not yet printed); large
        counts indicate a mid-run set-ingest stall.
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM card_catalog.unique_cards_ref ucr
        WHERE NOT EXISTS (
            SELECT 1 FROM card_catalog.card_version cv
            WHERE cv.unique_card_id = ucr.unique_card_id
        )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_external_id_value_collisions(self) -> int:
        """COUNT of (card_identifier_ref_id, value) tuples appearing more than once.

        The table has a UNIQUE constraint on (card_identifier_ref_id, value);
        any non-zero count indicates constraint bypass or replication desync.
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM (
            SELECT card_identifier_ref_id, value
            FROM card_catalog.card_external_identifier
            GROUP BY card_identifier_ref_id, value
            HAVING COUNT(*) > 1
        ) dup
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0
```

- [ ] **Step 3.4: Write the failing metric tests**

```python
# tests/unit/core/metrics/card_catalog/test_catalog_metrics.py
import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
import automana.core.metrics.card_catalog  # noqa: F401
from automana.core.metrics.card_catalog.catalog_metrics import (
    orphan_unique_cards,
    external_id_value_collision,
)

pytestmark = pytest.mark.unit


def _repo(orphans=0, collisions=0):
    repo = AsyncMock()
    repo.fetch_orphan_unique_cards_count.return_value = orphans
    repo.fetch_external_id_value_collisions.return_value = collisions
    return repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity",
    [(0, Severity.OK), (4, Severity.OK), (5, Severity.WARN), (49, Severity.WARN), (50, Severity.ERROR)],
)
async def test_orphan_unique_cards_severity_boundaries(n, severity):
    repo = _repo(orphans=n)
    result = await orphan_unique_cards(card_repository=repo)
    assert result.row_count == n
    cfg = MetricRegistry.get("card_catalog.print_coverage.orphan_unique_cards")
    assert MetricRegistry.evaluate(cfg, result.row_count) == severity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity", [(0, Severity.OK), (1, Severity.ERROR), (5, Severity.ERROR)]
)
async def test_external_id_value_collision_severity_boundaries(n, severity):
    repo = _repo(collisions=n)
    result = await external_id_value_collision(card_repository=repo)
    assert result.row_count == n
    cfg = MetricRegistry.get("card_catalog.duplicate_detection.external_id_value_collision")
    assert MetricRegistry.evaluate(cfg, result.row_count) == severity
```

- [ ] **Step 3.5: Run tests to verify they fail**

Run: `pytest tests/unit/core/metrics/card_catalog/test_catalog_metrics.py -v`
Expected: ImportError — module does not exist.

- [ ] **Step 3.6: Implement the metric module**

Create `src/automana/core/metrics/card_catalog/catalog_metrics.py`:

```python
"""card_catalog.* non-identifier metrics: catalog hygiene + collision detection."""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository


@MetricRegistry.register(
    path="card_catalog.print_coverage.orphan_unique_cards",
    category="health",
    description="Count of unique_cards_ref rows with zero card_version children.",
    severity=Threshold(warn=5, error=50, direction="higher_is_worse"),
    db_repositories=["card"],
)
async def orphan_unique_cards(card_repository: CardReferenceRepository) -> MetricResult:
    n = await card_repository.fetch_orphan_unique_cards_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="card_catalog.duplicate_detection.external_id_value_collision",
    category="health",
    description="Count of (card_identifier_ref_id, value) tuples appearing more than once (UNIQUE-constraint guard).",
    severity=Threshold(warn=1, error=1, direction="higher_is_worse"),
    db_repositories=["card"],
)
async def external_id_value_collision(card_repository: CardReferenceRepository) -> MetricResult:
    n = await card_repository.fetch_external_id_value_collisions()
    return MetricResult(row_count=n)
```

Update `src/automana/core/metrics/card_catalog/__init__.py`:

```python
from automana.core.metrics.card_catalog import identifier_metrics  # noqa: F401
from automana.core.metrics.card_catalog import catalog_metrics     # noqa: F401
```

- [ ] **Step 3.7: Run all card_catalog tests**

Run: `pytest tests/unit/core/metrics/card_catalog/ tests/unit/core/repositories/card_catalog/ -v`
Expected: all passing.

- [ ] **Step 3.8: Commit**

```bash
git add src/automana/core/metrics/card_catalog/ \
        tests/unit/core/metrics/card_catalog/test_catalog_metrics.py \
        tests/unit/core/repositories/card_catalog/test_card_repository_metrics.py \
        src/automana/core/repositories/card_catalog/card_repository.py
git commit -m "feat(metrics): card_catalog.print_coverage.orphan_unique_cards + duplicate_detection.external_id_value_collision"
```

---

## Task 4: Extract `_metric_runner.py` shared helper

The current `mtgstock_report.py` has four private helpers (`_normalize_names`, `_resolve_metric_function`, `_invoke_metric`, `_result_to_row`) that two more runners would copy verbatim. Extracting before adding the new runners avoids drift.

**Files:**
- Create: `src/automana/core/services/ops/_metric_runner.py`
- Test: `tests/unit/core/services/ops/test_metric_runner.py`

- [ ] **Step 4.1: Write the failing tests**

```python
# tests/unit/core/services/ops/test_metric_runner.py
"""Tests for _metric_runner.py — the shared dispatch helper used by every
ops.integrity.<family>_report service. Behavior asserted here mirrors what
test_mtgstock_report previously asserted directly against mtgstock_report;
mtgstock_report itself becomes a thin orchestration layer over this helper.
"""
import pytest
from unittest.mock import AsyncMock, patch

from automana.core.metrics.registry import MetricConfig, MetricRegistry, MetricResult, Severity, Threshold
from automana.core.services.ops._metric_runner import (
    _normalize_names,
    run_metric_report,
)

pytestmark = pytest.mark.unit


def test_normalize_names_none_returns_none():
    assert _normalize_names(None) is None


def test_normalize_names_string_splits_on_comma_and_strips():
    assert _normalize_names("a, b ,c") == ["a", "b", "c"]


def test_normalize_names_string_skips_empty_segments():
    assert _normalize_names("a, ,c,") == ["a", "c"]


def test_normalize_names_list_passes_through():
    assert _normalize_names(["a", "b"]) == ["a", "b"]


@pytest.fixture(autouse=True)
def _isolated_registry():
    saved = dict(MetricRegistry._metrics)
    MetricRegistry.clear()
    yield
    MetricRegistry._metrics.clear()
    MetricRegistry._metrics.update(saved)


@pytest.mark.asyncio
async def test_run_metric_report_invokes_only_signature_matching_kwargs():
    @MetricRegistry.register(
        path="x.takes_only_a",
        category="health",
        description="d",
        severity=Threshold(warn=1, error=2, direction="higher_is_worse"),
    )
    async def takes_only_a(a_repo) -> MetricResult:
        return MetricResult(row_count=0, details={"got": "a"})

    out = await run_metric_report(
        check_set="x_report",
        prefix="x.",
        metrics=None,
        category=None,
        repositories={"a_repo": "REPO_A", "b_repo": "REPO_B"},
        extra_kwargs=None,
    )
    assert out["check_set"] == "x_report"
    assert out["total_checks"] == 1
    assert out["rows"][0]["row_count"] == 0
    assert out["rows"][0]["details"]["got"] == "a"


@pytest.mark.asyncio
async def test_run_metric_report_swallows_metric_exceptions_as_error_rows():
    @MetricRegistry.register(
        path="x.boom",
        category="health",
        description="d",
        severity=Threshold(warn=1, error=2, direction="higher_is_worse"),
    )
    async def boom() -> MetricResult:
        raise RuntimeError("kaboom")

    out = await run_metric_report(
        check_set="x_report", prefix="x.", metrics=None, category=None,
        repositories={}, extra_kwargs=None,
    )
    assert out["error_count"] == 1
    err = out["errors"][0]
    assert err["check_name"] == "x.boom"
    assert err["severity"] == Severity.ERROR.value
    assert "RuntimeError" in err["details"]["exception"]


@pytest.mark.asyncio
async def test_run_metric_report_filters_by_explicit_names():
    @MetricRegistry.register(path="x.a", category="health", description="d", severity=None)
    async def a() -> MetricResult: return MetricResult(row_count=1)

    @MetricRegistry.register(path="x.b", category="health", description="d", severity=None)
    async def b() -> MetricResult: return MetricResult(row_count=2)

    out = await run_metric_report(
        check_set="x_report", prefix="x.", metrics="x.a", category=None,
        repositories={}, extra_kwargs=None,
    )
    assert [r["check_name"] for r in out["rows"]] == ["x.a"]


@pytest.mark.asyncio
async def test_run_metric_report_filters_by_category():
    @MetricRegistry.register(path="x.h", category="health", description="d", severity=None)
    async def h() -> MetricResult: return MetricResult(row_count=1)

    @MetricRegistry.register(path="x.v", category="volume", description="d", severity=None)
    async def v() -> MetricResult: return MetricResult(row_count=2)

    out = await run_metric_report(
        check_set="x_report", prefix="x.", metrics=None, category="health",
        repositories={}, extra_kwargs=None,
    )
    assert [r["check_name"] for r in out["rows"]] == ["x.h"]
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `pytest tests/unit/core/services/ops/test_metric_runner.py -v`
Expected: ImportError — `_metric_runner` does not exist.

- [ ] **Step 4.3: Implement the helper**

Create `src/automana/core/services/ops/_metric_runner.py`:

```python
"""Shared dispatch helper for ops.integrity.<family>_report services.

Mirrors the original `mtgstock_report.py` private helpers verbatim, then
generalizes the kwargs injection so every runner can declare its own
repository set without copy-pasting the dispatch loop.
"""
from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any

from automana.core.metrics import MetricConfig, MetricRegistry, MetricResult, Severity
from automana.core.services.ops.integrity_checks import _build_report

logger = logging.getLogger(__name__)


def _normalize_names(metrics: str | list[str] | None) -> list[str] | None:
    """Accept either a comma-separated CLI string or a list; return list or None."""
    if metrics is None:
        return None
    if isinstance(metrics, str):
        return [m.strip() for m in metrics.split(",") if m.strip()]
    return list(metrics)


def _resolve_metric_function(config: MetricConfig):
    module = importlib.import_module(config.module)
    return getattr(module, config.function)


async def _invoke_metric(config: MetricConfig, candidate_kwargs: dict[str, Any]) -> MetricResult:
    """Invoke a metric function passing only the kwargs its signature accepts."""
    func = _resolve_metric_function(config)
    allowed = set(inspect.signature(func).parameters.keys())
    kwargs = {k: v for k, v in candidate_kwargs.items() if k in allowed}
    return await func(**kwargs)


def _result_to_row(config: MetricConfig, result: MetricResult) -> dict[str, Any]:
    severity = MetricRegistry.evaluate(config, result.row_count)
    return {
        "check_name": config.path,
        "severity": severity.value if isinstance(severity, Severity) else str(severity),
        "row_count": result.row_count,
        "details": {
            **result.details,
            "description": config.description,
            "category": config.category,
        },
    }


async def run_metric_report(
    *,
    check_set: str,
    prefix: str,
    metrics: str | list[str] | None,
    category: str | None,
    repositories: dict[str, Any],
    extra_kwargs: dict[str, Any] | None = None,
) -> dict:
    """Run every metric matching prefix + filters and return the standard envelope.

    `repositories` is the full kwargs dict the caller wants to make available
    (e.g. {"price_repository": ..., "ops_repository": ...}). `extra_kwargs`
    folds in non-repository values like `ingestion_run_id`. Per metric, only
    the kwargs whose names match the function signature are passed.
    """
    names = _normalize_names(metrics)
    selected = MetricRegistry.select(names=names, category=category, prefix=prefix)

    if not selected:
        logger.warning(
            "metric_report_no_metrics_selected",
            extra={"check_set": check_set, "metrics": names, "category": category},
        )

    candidate_kwargs: dict[str, Any] = {**repositories, **(extra_kwargs or {})}
    rows: list[dict[str, Any]] = []
    for config in selected:
        try:
            result = await _invoke_metric(config, candidate_kwargs)
        except Exception as exc:  # noqa: BLE001 — one bad metric must not take the report down
            logger.exception("metric_invocation_failed", extra={"metric": config.path})
            rows.append({
                "check_name": config.path,
                "severity": Severity.ERROR.value,
                "row_count": None,
                "details": {
                    "exception": f"{type(exc).__name__}: {exc}",
                    "description": config.description,
                    "category": config.category,
                },
            })
            continue
        rows.append(_result_to_row(config, result))

    return _build_report(check_set, rows)
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run: `pytest tests/unit/core/services/ops/test_metric_runner.py -v`
Expected: 9 passing.

- [ ] **Step 4.5: Commit**

```bash
git add src/automana/core/services/ops/_metric_runner.py \
        tests/unit/core/services/ops/test_metric_runner.py
git commit -m "feat(metrics): extract shared _metric_runner helper for ops.integrity.*_report services"
```

---

## Task 5: Migrate `mtgstock_report` to use `_metric_runner`

Regression task. The existing tests in `tests/unit/core/services/ops/test_mtgstock_report.py` must continue to pass unchanged.

**Files:**
- Modify: `src/automana/core/services/ops/mtgstock_report.py`

- [ ] **Step 5.1: Run existing tests as the baseline**

Run: `pytest tests/unit/core/services/ops/test_mtgstock_report.py -v`
Record the pass count. Expected: all green before changes.

- [ ] **Step 5.2: Replace the file body**

Overwrite `src/automana/core/services/ops/mtgstock_report.py` with:

```python
"""MTGStock sanity / run-summary report.

A runner service that dispatches a selected subset of registered
``mtgstock.*`` metrics via the shared `_metric_runner.run_metric_report`
helper.
"""
from __future__ import annotations

import logging

# Importing the package triggers registration of all mtgstock.* metrics.
import automana.core.metrics.mtgstock  # noqa: F401
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops._metric_runner import _normalize_names, run_metric_report

logger = logging.getLogger(__name__)

# Re-exported so existing tests that import _normalize_names from this module
# keep working without modification.
__all__ = ["mtgstock_report", "_normalize_names"]


@ServiceRegistry.register(
    "ops.integrity.mtgstock_report",
    db_repositories=["price", "ops"],
)
async def mtgstock_report(
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
    ingestion_run_id: int | None = None,
) -> dict:
    """Run the mtgstock sanity report. See `MetricRegistry` docs for selection semantics."""
    return await run_metric_report(
        check_set="mtgstock_report",
        prefix="mtgstock.",
        metrics=metrics,
        category=category,
        repositories={
            "price_repository": price_repository,
            "ops_repository": ops_repository,
        },
        extra_kwargs={"ingestion_run_id": ingestion_run_id},
    )
```

- [ ] **Step 5.3: Run the existing mtgstock_report tests**

Run: `pytest tests/unit/core/services/ops/test_mtgstock_report.py -v`
Expected: same pass count as Step 5.1 — zero regressions.

- [ ] **Step 5.4: Run the full ops test suite**

Run: `pytest tests/unit/core/services/ops/ -v`
Expected: all green.

- [ ] **Step 5.5: Commit**

```bash
git add src/automana/core/services/ops/mtgstock_report.py
git commit -m "refactor(metrics): migrate mtgstock_report to shared _metric_runner helper"
```

---

## Task 6: `ops.integrity.card_catalog_report` runner

**Files:**
- Create: `src/automana/core/services/ops/card_catalog_report.py`
- Test: `tests/unit/core/services/ops/test_card_catalog_report.py`

- [ ] **Step 6.1: Write the failing tests**

```python
# tests/unit/core/services/ops/test_card_catalog_report.py
"""Tests for ops.integrity.card_catalog_report.

The runner is a thin wrapper around _metric_runner.run_metric_report (already
unit-tested) — these tests assert the wiring: prefix, check_set, repositories
dict, and that the 8 card_catalog.* metrics are actually selectable through it.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.services.ops.card_catalog_report import card_catalog_report

pytestmark = pytest.mark.unit


def _repos():
    card = AsyncMock()
    card.fetch_identifier_coverage_pct.return_value = {"covered": 100, "total": 100, "pct": 100.0}
    card.fetch_identifier_value_count.return_value = 0
    card.fetch_orphan_unique_cards_count.return_value = 0
    card.fetch_external_id_value_collisions.return_value = 0
    ops = AsyncMock()
    return card, ops


@pytest.mark.asyncio
async def test_card_catalog_report_runs_all_eight_metrics_with_no_filter():
    card, ops = _repos()
    out = await card_catalog_report(card_repository=card, ops_repository=ops)
    assert out["check_set"] == "card_catalog_report"
    assert out["total_checks"] == 8
    paths = {r["check_name"] for r in out["rows"]}
    expected = {
        "card_catalog.identifier_coverage.scryfall_id",
        "card_catalog.identifier_coverage.oracle_id",
        "card_catalog.identifier_coverage.tcgplayer_id",
        "card_catalog.identifier_coverage.cardmarket_id",
        "card_catalog.identifier_coverage.multiverse_id",
        "card_catalog.identifier_coverage.tcgplayer_etched_id",
        "card_catalog.print_coverage.orphan_unique_cards",
        "card_catalog.duplicate_detection.external_id_value_collision",
    }
    assert paths == expected


@pytest.mark.asyncio
async def test_card_catalog_report_category_filter_health_only():
    card, ops = _repos()
    out = await card_catalog_report(card_repository=card, ops_repository=ops, category="health")
    paths = {r["check_name"] for r in out["rows"]}
    # multiverse_id and tcgplayer_etched_id are category="volume" — should be excluded
    assert "card_catalog.identifier_coverage.multiverse_id" not in paths
    assert "card_catalog.identifier_coverage.tcgplayer_etched_id" not in paths
    assert "card_catalog.identifier_coverage.scryfall_id" in paths


@pytest.mark.asyncio
async def test_card_catalog_report_explicit_metric_string_runs_only_that_one():
    card, ops = _repos()
    out = await card_catalog_report(
        card_repository=card, ops_repository=ops,
        metrics="card_catalog.identifier_coverage.scryfall_id",
    )
    assert out["total_checks"] == 1
    assert out["rows"][0]["check_name"] == "card_catalog.identifier_coverage.scryfall_id"


@pytest.mark.asyncio
async def test_card_catalog_report_one_failing_metric_does_not_kill_report():
    card, ops = _repos()
    card.fetch_identifier_coverage_pct.side_effect = RuntimeError("db down")
    out = await card_catalog_report(card_repository=card, ops_repository=ops)
    # All 4 pct-coverage metrics fail → 4 errors. The other 4 metrics still run.
    assert out["error_count"] == 4
    assert out["total_checks"] == 8
```

- [ ] **Step 6.2: Run tests to verify they fail**

Run: `pytest tests/unit/core/services/ops/test_card_catalog_report.py -v`
Expected: ImportError.

- [ ] **Step 6.3: Implement the runner**

Create `src/automana/core/services/ops/card_catalog_report.py`:

```python
"""Card-catalog sanity report. Runs every registered card_catalog.* metric."""
from __future__ import annotations

import logging

import automana.core.metrics.card_catalog  # noqa: F401  — register card_catalog.* metrics
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops._metric_runner import run_metric_report

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "ops.integrity.card_catalog_report",
    db_repositories=["card", "ops"],
)
async def card_catalog_report(
    card_repository: CardReferenceRepository,
    ops_repository: OpsRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
) -> dict:
    """Run the card_catalog sanity report.

    Args:
        metrics:  comma-separated string (CLI) or list of metric paths.
        category: filter by category — ``health``, ``volume``, ``timing``, ``status``.
    """
    return await run_metric_report(
        check_set="card_catalog_report",
        prefix="card_catalog.",
        metrics=metrics,
        category=category,
        repositories={
            "card_repository": card_repository,
            "ops_repository": ops_repository,
        },
    )
```

- [ ] **Step 6.4: Run tests**

Run: `pytest tests/unit/core/services/ops/test_card_catalog_report.py -v`
Expected: 4 passing.

- [ ] **Step 6.5: Commit**

```bash
git add src/automana/core/services/ops/card_catalog_report.py \
        tests/unit/core/services/ops/test_card_catalog_report.py
git commit -m "feat(metrics): ops.integrity.card_catalog_report runner service"
```

---

## Task 7: `OpsRepository.fetch_latest_successful_run_ended_at`

**Files:**
- Modify: `src/automana/core/repositories/ops/ops_repository.py`
- Test: `tests/unit/core/repositories/ops/test_ops_repository_freshness.py` (create)

- [ ] **Step 7.1: Write the failing test**

```python
# tests/unit/core/repositories/ops/test_ops_repository_freshness.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from automana.core.repositories.ops.ops_repository import OpsRepository

pytestmark = pytest.mark.unit


def _repo(rows):
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_fetch_latest_successful_run_ended_at_returns_datetime():
    ts = datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc)
    repo = _repo([{"ended_at": ts}])
    out = await repo.fetch_latest_successful_run_ended_at("mtg_stock_all")
    assert out == ts


@pytest.mark.asyncio
async def test_fetch_latest_successful_run_ended_at_none_when_no_runs():
    repo = _repo([])
    assert await repo.fetch_latest_successful_run_ended_at("mtg_stock_all") is None


@pytest.mark.asyncio
async def test_fetch_latest_successful_run_ended_at_passes_pipeline_arg():
    repo = _repo([])
    await repo.fetch_latest_successful_run_ended_at("mtgjson_daily")
    args = repo.execute_query.await_args.args
    assert args[1] == ("mtgjson_daily",)
```

- [ ] **Step 7.2: Run tests to verify they fail**

Run: `pytest tests/unit/core/repositories/ops/test_ops_repository_freshness.py -v`
Expected: AttributeError.

- [ ] **Step 7.3: Implement the method**

Append to `class OpsRepository`:

```python
    async def fetch_latest_successful_run_ended_at(self, pipeline_name: str):
        """Return ended_at of the most recent ingestion_runs row with status='success'
        for the given pipeline. Used by pricing freshness metrics to compute lag."""
        query = """
        SELECT ended_at
        FROM ops.ingestion_runs
        WHERE pipeline_name = $1 AND status = 'success' AND ended_at IS NOT NULL
        ORDER BY ended_at DESC
        LIMIT 1
        """
        rows = await self.execute_query(query, (pipeline_name,))
        return rows[0]["ended_at"] if rows else None
```

- [ ] **Step 7.4: Run tests**

Run: `pytest tests/unit/core/repositories/ops/test_ops_repository_freshness.py -v`
Expected: 3 passing.

- [ ] **Step 7.5: Commit**

```bash
git add src/automana/core/repositories/ops/ops_repository.py \
        tests/unit/core/repositories/ops/test_ops_repository_freshness.py
git commit -m "feat(repo): OpsRepository.fetch_latest_successful_run_ended_at"
```

---

## Task 8: Pricing freshness + coverage repository methods

**Files:**
- Modify: `src/automana/core/repositories/app_integration/mtg_stock/price_repository.py`
- Test: `tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py` (create)

- [ ] **Step 8.1: Write the failing tests**

```python
# tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py
"""Tests for the metric-support read methods on PriceRepository.

Methods are read-only and feed the pricing.* metric family. Covers freshness
(max age, per-source lag), coverage (per-source observation coverage),
referential soft-integrity, staging drain, and PK-collision detection.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.repositories.app_integration.mtg_stock.price_repository import (
    PriceRepository,
)

pytestmark = pytest.mark.unit


def _repo(rows):
    repo = PriceRepository.__new__(PriceRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_fetch_max_observation_age_days_returns_int():
    repo = _repo([{"age_days": 1}])
    assert await repo.fetch_max_observation_age_days() == 1


@pytest.mark.asyncio
async def test_fetch_max_observation_age_days_none_when_table_empty():
    repo = _repo([{"age_days": None}])
    assert await repo.fetch_max_observation_age_days() is None


@pytest.mark.asyncio
async def test_fetch_per_source_lag_hours_returns_dict():
    repo = _repo([
        {"source_code": "tcgplayer", "lag_hours": 2.5},
        {"source_code": "mtgstocks", "lag_hours": 26.0},
    ])
    out = await repo.fetch_per_source_lag_hours()
    assert out == {"tcgplayer": 2.5, "mtgstocks": 26.0}


@pytest.mark.asyncio
async def test_fetch_per_source_observation_coverage_pct_returns_dict():
    repo = _repo([
        {"source_code": "tcgplayer", "pct": 90.0},
        {"source_code": "mtgstocks", "pct": 60.0},
    ])
    out = await repo.fetch_per_source_observation_coverage_pct(window_days=30)
    assert out == {"tcgplayer": 90.0, "mtgstocks": 60.0}
    args = repo.execute_query.await_args.args
    assert args[1] == (30,)
```

- [ ] **Step 8.2: Run tests to verify they fail**

Run: `pytest tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py -v`
Expected: AttributeError on each.

- [ ] **Step 8.3: Implement the three methods**

Append to `class PriceRepository`:

```python
    async def fetch_max_observation_age_days(self) -> int | None:
        """Days since the most recent price_observation.ts_date across all sources."""
        query = """
        SELECT (CURRENT_DATE - MAX(ts_date))::int AS age_days
        FROM pricing.price_observation
        """
        rows = await self.execute_query(query, ())
        return rows[0]["age_days"] if rows else None

    async def fetch_per_source_lag_hours(self) -> dict[str, float | None]:
        """{source_code: hours_since_latest_observation} for every price_source."""
        query = """
        SELECT
            ps.code AS source_code,
            EXTRACT(EPOCH FROM (now() - MAX(po.created_at))) / 3600.0 AS lag_hours
        FROM pricing.price_source ps
        LEFT JOIN pricing.source_product sp ON sp.source_id = ps.source_id
        LEFT JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
        GROUP BY ps.code
        """
        rows = await self.execute_query(query, ())
        return {r["source_code"]: r["lag_hours"] for r in rows}

    async def fetch_per_source_observation_coverage_pct(
        self, window_days: int = 30
    ) -> dict[str, float | None]:
        """{source_code: pct} where pct is fraction of source_product rows with a
        price_observation in the last `window_days` days."""
        query = """
        SELECT
            ps.code AS source_code,
            CASE WHEN COUNT(sp.source_product_id) = 0 THEN NULL
                 ELSE ROUND(
                     100.0 * COUNT(DISTINCT po.source_product_id)
                     / NULLIF(COUNT(DISTINCT sp.source_product_id), 0), 2
                 )::float
            END AS pct
        FROM pricing.price_source ps
        LEFT JOIN pricing.source_product sp ON sp.source_id = ps.source_id
        LEFT JOIN pricing.price_observation po
               ON po.source_product_id = sp.source_product_id
              AND po.ts_date >= CURRENT_DATE - ($1::int || ' days')::interval
        GROUP BY ps.code
        """
        rows = await self.execute_query(query, (window_days,))
        return {r["source_code"]: r["pct"] for r in rows}
```

- [ ] **Step 8.4: Run tests**

Run: `pytest tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py -v`
Expected: 4 passing.

- [ ] **Step 8.5: Commit**

```bash
git add src/automana/core/repositories/app_integration/mtg_stock/price_repository.py \
        tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py
git commit -m "feat(repo): PriceRepository freshness + per-source coverage methods"
```

---

## Task 9: Pricing referential + staging + collision repository methods

**Files:**
- Modify: `src/automana/core/repositories/app_integration/mtg_stock/price_repository.py`
- Modify: `tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py`

- [ ] **Step 9.1: Append the failing tests**

```python
@pytest.mark.asyncio
async def test_fetch_orphan_product_ref_mtg_count_returns_int():
    repo = _repo([{"n": 3}])
    assert await repo.fetch_orphan_product_ref_mtg_count() == 3


@pytest.mark.asyncio
async def test_fetch_orphan_observation_count_returns_int():
    repo = _repo([{"n": 0}])
    assert await repo.fetch_orphan_observation_count() == 0


@pytest.mark.asyncio
async def test_fetch_stg_residual_count_returns_int():
    repo = _repo([{"n": 1234}])
    assert await repo.fetch_stg_residual_count() == 1234


@pytest.mark.asyncio
async def test_fetch_observation_pk_collision_count_returns_int():
    repo = _repo([{"n": 0}])
    assert await repo.fetch_observation_pk_collision_count() == 0
```

- [ ] **Step 9.2: Run to verify they fail**

Run: `pytest tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py -v -k "orphan or stg_residual or pk_collision"`
Expected: AttributeError on each.

- [ ] **Step 9.3: Implement the four methods**

Append to `class PriceRepository`:

```python
    async def fetch_orphan_product_ref_mtg_count(self) -> int:
        """pricing.product_ref rows whose game_id matches the 'mtg' card_game row
        but have no pricing.mtg_card_products row."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.product_ref pr
        JOIN pricing.card_game cg ON cg.game_id = pr.game_id
        WHERE cg.code = 'mtg'
          AND NOT EXISTS (
              SELECT 1 FROM pricing.mtg_card_products mcp
              WHERE mcp.product_id = pr.product_id
          )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_orphan_observation_count(self) -> int:
        """price_observation rows whose source_product_id no longer exists in
        source_product. Hard FK should make this 0."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM pricing.price_observation po
        WHERE NOT EXISTS (
            SELECT 1 FROM pricing.source_product sp
            WHERE sp.source_product_id = po.source_product_id
        )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_stg_residual_count(self) -> int:
        """Estimated row count of stg_price_observation via pg_class.reltuples.
        Fast (no scan); good enough for a residual-drain alarm."""
        query = """
        SELECT reltuples::bigint AS n
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'pricing' AND c.relname = 'stg_price_observation'
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_observation_pk_collision_count(self) -> int:
        """Composite-PK violations in price_observation. Should always be 0."""
        query = """
        SELECT COUNT(*)::int AS n
        FROM (
            SELECT 1
            FROM pricing.price_observation
            GROUP BY ts_date, source_product_id, price_type_id, finish_id,
                     condition_id, language_id, data_provider_id
            HAVING COUNT(*) > 1
        ) dup
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0
```

- [ ] **Step 9.4: Run tests**

Run: `pytest tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py -v`
Expected: all 8 passing.

- [ ] **Step 9.5: Commit**

```bash
git add src/automana/core/repositories/app_integration/mtg_stock/price_repository.py \
        tests/unit/core/repositories/app_integration/mtg_stock/test_price_repository_metrics.py
git commit -m "feat(repo): PriceRepository referential + staging + PK-collision methods"
```

---

## Task 10: Pricing freshness + coverage metrics

**Files:**
- Create: `src/automana/core/metrics/pricing/__init__.py`
- Create: `src/automana/core/metrics/pricing/freshness_metrics.py`
- Create: `src/automana/core/metrics/pricing/coverage_metrics.py`
- Test: `tests/unit/core/metrics/pricing/__init__.py` (empty)
- Test: `tests/unit/core/metrics/pricing/test_freshness_metrics.py`
- Test: `tests/unit/core/metrics/pricing/test_coverage_metrics.py`

- [ ] **Step 10.1: Write the failing freshness tests**

```python
# tests/unit/core/metrics/pricing/test_freshness_metrics.py
import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
import automana.core.metrics.pricing  # noqa: F401
from automana.core.metrics.pricing.freshness_metrics import (
    price_observation_max_age_days,
    max_per_source_lag_hours,
)

pytestmark = pytest.mark.unit


def _price_repo(max_age=None, per_source_lag=None):
    repo = AsyncMock()
    repo.fetch_max_observation_age_days.return_value = max_age
    repo.fetch_per_source_lag_hours.return_value = per_source_lag or {}
    return repo


@pytest.mark.asyncio
async def test_price_observation_max_age_days_value_and_severity():
    repo = _price_repo(max_age=1)
    result = await price_observation_max_age_days(price_repository=repo)
    assert result.row_count == 1
    cfg = MetricRegistry.get("pricing.freshness.price_observation_max_age_days")
    assert MetricRegistry.evaluate(cfg, 1) == Severity.OK
    assert MetricRegistry.evaluate(cfg, 3) == Severity.WARN
    assert MetricRegistry.evaluate(cfg, 8) == Severity.ERROR


@pytest.mark.asyncio
async def test_price_observation_max_age_days_none_returns_none():
    repo = _price_repo(max_age=None)
    result = await price_observation_max_age_days(price_repository=repo)
    assert result.row_count is None


@pytest.mark.asyncio
async def test_max_per_source_lag_hours_picks_max_value_and_carries_per_source_details():
    repo = _price_repo(per_source_lag={"tcgplayer": 2.5, "mtgstocks": 26.0, "cardmarket": None})
    result = await max_per_source_lag_hours(price_repository=repo)
    assert result.row_count == 26.0
    assert result.details["per_source"] == {"tcgplayer": 2.5, "mtgstocks": 26.0, "cardmarket": None}


@pytest.mark.asyncio
async def test_max_per_source_lag_hours_empty_dict_returns_none():
    repo = _price_repo(per_source_lag={})
    result = await max_per_source_lag_hours(price_repository=repo)
    assert result.row_count is None
```

- [ ] **Step 10.2: Write the failing coverage tests**

```python
# tests/unit/core/metrics/pricing/test_coverage_metrics.py
import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
import automana.core.metrics.pricing  # noqa: F401
from automana.core.metrics.pricing.coverage_metrics import (
    min_per_source_observation_coverage_pct,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_min_per_source_observation_coverage_picks_min_value():
    repo = AsyncMock()
    repo.fetch_per_source_observation_coverage_pct.return_value = {
        "tcgplayer": 90.0, "mtgstocks": 30.0, "cardmarket": 60.0,
    }
    result = await min_per_source_observation_coverage_pct(price_repository=repo)
    assert result.row_count == 30.0
    assert result.details["per_source"] == {"tcgplayer": 90.0, "mtgstocks": 30.0, "cardmarket": 60.0}
    cfg = MetricRegistry.get("pricing.coverage.min_per_source_observation_coverage_pct")
    assert MetricRegistry.evaluate(cfg, 30.0) == Severity.WARN


@pytest.mark.asyncio
async def test_min_per_source_observation_coverage_excludes_none_for_min():
    repo = AsyncMock()
    repo.fetch_per_source_observation_coverage_pct.return_value = {
        "tcgplayer": 90.0, "cardmarket": None,
    }
    result = await min_per_source_observation_coverage_pct(price_repository=repo)
    assert result.row_count == 90.0


@pytest.mark.asyncio
async def test_min_per_source_observation_coverage_empty_returns_none():
    repo = AsyncMock()
    repo.fetch_per_source_observation_coverage_pct.return_value = {}
    result = await min_per_source_observation_coverage_pct(price_repository=repo)
    assert result.row_count is None
```

- [ ] **Step 10.3: Run tests to verify they fail**

Run: `pytest tests/unit/core/metrics/pricing/ -v`
Expected: ImportError — package does not exist.

- [ ] **Step 10.4: Create the package + freshness module**

Create `src/automana/core/metrics/pricing/__init__.py`:

```python
from automana.core.metrics.pricing import freshness_metrics  # noqa: F401
from automana.core.metrics.pricing import coverage_metrics   # noqa: F401
```

Create `src/automana/core/metrics/pricing/freshness_metrics.py`:

```python
"""pricing.freshness.* — staleness detection across pricing sources."""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository


@MetricRegistry.register(
    path="pricing.freshness.price_observation_max_age_days",
    category="timing",
    description="Days since the most recent pricing.price_observation.ts_date across all sources.",
    severity=Threshold(warn=2, error=7, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def price_observation_max_age_days(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_max_observation_age_days()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.freshness.max_per_source_lag_hours",
    category="timing",
    description="Hours since the latest observation per source. Headline = MAX across sources; details carries per-source breakdown.",
    severity=Threshold(warn=48, error=120, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def max_per_source_lag_hours(price_repository: PriceRepository) -> MetricResult:
    per_source = await price_repository.fetch_per_source_lag_hours()
    non_null = [v for v in per_source.values() if v is not None]
    headline = max(non_null) if non_null else None
    return MetricResult(row_count=headline, details={"per_source": per_source})
```

Create `src/automana/core/metrics/pricing/coverage_metrics.py`:

```python
"""pricing.coverage.* — per-source observation coverage."""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository


@MetricRegistry.register(
    path="pricing.coverage.min_per_source_observation_coverage_pct",
    category="health",
    description="MIN across sources of % of source_product rows with a price_observation in the last 30 days.",
    severity=Threshold(warn=50, error=20, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def min_per_source_observation_coverage_pct(
    price_repository: PriceRepository,
) -> MetricResult:
    per_source = await price_repository.fetch_per_source_observation_coverage_pct()
    non_null = [v for v in per_source.values() if v is not None]
    headline = min(non_null) if non_null else None
    return MetricResult(row_count=headline, details={"per_source": per_source})
```

- [ ] **Step 10.5: Run tests**

Run: `pytest tests/unit/core/metrics/pricing/ -v`
Expected: 7 passing.

- [ ] **Step 10.6: Commit**

```bash
git add src/automana/core/metrics/pricing/ \
        tests/unit/core/metrics/pricing/
git commit -m "feat(metrics): pricing.freshness.* + pricing.coverage.* metrics"
```

---

## Task 11: Pricing integrity metrics (referential + staging + duplicate)

**Files:**
- Create: `src/automana/core/metrics/pricing/integrity_metrics.py`
- Modify: `src/automana/core/metrics/pricing/__init__.py`
- Test: `tests/unit/core/metrics/pricing/test_integrity_metrics.py`

- [ ] **Step 11.1: Write the failing tests**

```python
# tests/unit/core/metrics/pricing/test_integrity_metrics.py
import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
import automana.core.metrics.pricing  # noqa: F401
from automana.core.metrics.pricing.integrity_metrics import (
    product_without_mtg_card_products,
    observation_without_source_product,
    stg_price_observation_residual_count,
    observation_duplicates_on_pk,
)

pytestmark = pytest.mark.unit


def _repo(orphan_pr=0, orphan_obs=0, residual=0, pk_dups=0):
    repo = AsyncMock()
    repo.fetch_orphan_product_ref_mtg_count.return_value = orphan_pr
    repo.fetch_orphan_observation_count.return_value = orphan_obs
    repo.fetch_stg_residual_count.return_value = residual
    repo.fetch_observation_pk_collision_count.return_value = pk_dups
    return repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity", [(0, Severity.OK), (5, Severity.WARN), (20, Severity.ERROR)]
)
async def test_product_without_mtg_card_products_severity(n, severity):
    repo = _repo(orphan_pr=n)
    result = await product_without_mtg_card_products(price_repository=repo)
    assert result.row_count == n
    cfg = MetricRegistry.get("pricing.referential.product_without_mtg_card_products")
    assert MetricRegistry.evaluate(cfg, n) == severity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity", [(0, Severity.OK), (1, Severity.WARN), (10, Severity.ERROR)]
)
async def test_observation_without_source_product_severity(n, severity):
    repo = _repo(orphan_obs=n)
    result = await observation_without_source_product(price_repository=repo)
    assert MetricRegistry.evaluate(
        MetricRegistry.get("pricing.referential.observation_without_source_product"), n
    ) == severity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n,severity",
    [(0, Severity.OK), (999_999, Severity.OK), (1_000_000, Severity.WARN), (5_000_000, Severity.ERROR)],
)
async def test_stg_residual_severity(n, severity):
    repo = _repo(residual=n)
    result = await stg_price_observation_residual_count(price_repository=repo)
    assert result.row_count == n
    assert MetricRegistry.evaluate(
        MetricRegistry.get("pricing.staging.stg_price_observation_residual_count"), n
    ) == severity


@pytest.mark.asyncio
@pytest.mark.parametrize("n,severity", [(0, Severity.OK), (1, Severity.ERROR)])
async def test_pk_collision_severity(n, severity):
    repo = _repo(pk_dups=n)
    result = await observation_duplicates_on_pk(price_repository=repo)
    assert MetricRegistry.evaluate(
        MetricRegistry.get("pricing.duplicate_detection.observation_duplicates_on_pk"), n
    ) == severity
```

- [ ] **Step 11.2: Run tests to verify they fail**

Run: `pytest tests/unit/core/metrics/pricing/test_integrity_metrics.py -v`
Expected: ImportError.

- [ ] **Step 11.3: Implement the metric module**

Create `src/automana/core/metrics/pricing/integrity_metrics.py`:

```python
"""pricing.* — referential soft-integrity, staging drain, duplicate detection."""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository


@MetricRegistry.register(
    path="pricing.referential.product_without_mtg_card_products",
    category="health",
    description="pricing.product_ref rows with game=mtg but no mtg_card_products row.",
    severity=Threshold(warn=5, error=20, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def product_without_mtg_card_products(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_orphan_product_ref_mtg_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.referential.observation_without_source_product",
    category="health",
    description="pricing.price_observation rows whose source_product_id no longer exists in source_product.",
    severity=Threshold(warn=1, error=10, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def observation_without_source_product(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_orphan_observation_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.staging.stg_price_observation_residual_count",
    category="volume",
    description="Estimated row count of stg_price_observation (should drain to ~0 between runs).",
    severity=Threshold(warn=1_000_000, error=5_000_000, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def stg_price_observation_residual_count(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_stg_residual_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.duplicate_detection.observation_duplicates_on_pk",
    category="health",
    description="Composite-PK violations in price_observation (should always be 0).",
    severity=Threshold(warn=1, error=1, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def observation_duplicates_on_pk(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_observation_pk_collision_count()
    return MetricResult(row_count=n)
```

Update `src/automana/core/metrics/pricing/__init__.py`:

```python
from automana.core.metrics.pricing import freshness_metrics  # noqa: F401
from automana.core.metrics.pricing import coverage_metrics   # noqa: F401
from automana.core.metrics.pricing import integrity_metrics  # noqa: F401
```

- [ ] **Step 11.4: Run all pricing-metric tests**

Run: `pytest tests/unit/core/metrics/pricing/ -v`
Expected: all passing (≥ 14 cases including parametrized).

- [ ] **Step 11.5: Commit**

```bash
git add src/automana/core/metrics/pricing/ \
        tests/unit/core/metrics/pricing/test_integrity_metrics.py
git commit -m "feat(metrics): pricing.* referential + staging + PK-collision metrics"
```

---

## Task 12: `ops.integrity.pricing_report` runner

**Files:**
- Create: `src/automana/core/services/ops/pricing_report.py`
- Test: `tests/unit/core/services/ops/test_pricing_report.py`

- [ ] **Step 12.1: Write the failing tests**

```python
# tests/unit/core/services/ops/test_pricing_report.py
import pytest
from unittest.mock import AsyncMock

from automana.core.services.ops.pricing_report import pricing_report

pytestmark = pytest.mark.unit


def _repos():
    price = AsyncMock()
    price.fetch_max_observation_age_days.return_value = 1
    price.fetch_per_source_lag_hours.return_value = {"tcgplayer": 2.0, "mtgstocks": 25.0}
    price.fetch_per_source_observation_coverage_pct.return_value = {"tcgplayer": 95.0}
    price.fetch_orphan_product_ref_mtg_count.return_value = 0
    price.fetch_orphan_observation_count.return_value = 0
    price.fetch_stg_residual_count.return_value = 0
    price.fetch_observation_pk_collision_count.return_value = 0
    ops = AsyncMock()
    return price, ops


@pytest.mark.asyncio
async def test_pricing_report_runs_all_seven_metrics_with_no_filter():
    price, ops = _repos()
    out = await pricing_report(price_repository=price, ops_repository=ops)
    assert out["check_set"] == "pricing_report"
    assert out["total_checks"] == 7
    paths = {r["check_name"] for r in out["rows"]}
    expected = {
        "pricing.freshness.price_observation_max_age_days",
        "pricing.freshness.max_per_source_lag_hours",
        "pricing.coverage.min_per_source_observation_coverage_pct",
        "pricing.referential.product_without_mtg_card_products",
        "pricing.referential.observation_without_source_product",
        "pricing.staging.stg_price_observation_residual_count",
        "pricing.duplicate_detection.observation_duplicates_on_pk",
    }
    assert paths == expected


@pytest.mark.asyncio
async def test_pricing_report_category_filter_health_only_excludes_volume_and_timing():
    price, ops = _repos()
    out = await pricing_report(price_repository=price, ops_repository=ops, category="health")
    paths = {r["check_name"] for r in out["rows"]}
    # max_age (timing), max_per_source_lag (timing), residual (volume) excluded
    assert "pricing.freshness.price_observation_max_age_days" not in paths
    assert "pricing.staging.stg_price_observation_residual_count" not in paths


@pytest.mark.asyncio
async def test_pricing_report_one_failing_metric_does_not_kill_report():
    price, ops = _repos()
    price.fetch_max_observation_age_days.side_effect = RuntimeError("db down")
    out = await pricing_report(price_repository=price, ops_repository=ops)
    assert out["error_count"] == 1
    assert out["total_checks"] == 7
```

- [ ] **Step 12.2: Run to verify they fail**

Run: `pytest tests/unit/core/services/ops/test_pricing_report.py -v`
Expected: ImportError.

- [ ] **Step 12.3: Implement the runner**

Create `src/automana/core/services/ops/pricing_report.py`:

```python
"""Pricing data-quality report. Runs every registered pricing.* metric."""
from __future__ import annotations

import logging

import automana.core.metrics.pricing  # noqa: F401  — register pricing.* metrics
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops._metric_runner import run_metric_report

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "ops.integrity.pricing_report",
    db_repositories=["price", "ops"],
)
async def pricing_report(
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
) -> dict:
    """Run the pricing data-quality report.

    Args:
        metrics:  comma-separated string (CLI) or list of metric paths.
        category: filter by category — ``health``, ``volume``, ``timing``, ``status``.
    """
    return await run_metric_report(
        check_set="pricing_report",
        prefix="pricing.",
        metrics=metrics,
        category=category,
        repositories={
            "price_repository": price_repository,
            "ops_repository": ops_repository,
        },
    )
```

- [ ] **Step 12.4: Run tests**

Run: `pytest tests/unit/core/services/ops/test_pricing_report.py -v`
Expected: 3 passing.

- [ ] **Step 12.5: Commit**

```bash
git add src/automana/core/services/ops/pricing_report.py \
        tests/unit/core/services/ops/test_pricing_report.py
git commit -m "feat(metrics): ops.integrity.pricing_report runner service"
```

---

## Task 13: Register both runners in `SERVICE_MODULES`

**Files:**
- Modify: `src/automana/core/service_modules.py`

- [ ] **Step 13.1: Add the two new module paths to all three SERVICE_MODULES keys**

In `src/automana/core/service_modules.py`, add after the existing `"automana.core.services.ops.mtgstock_report",` line in **each** of the three lists (`"backend"`, `"celery"`, `"all"`):

```python
            "automana.core.services.ops.card_catalog_report",
            "automana.core.services.ops.pricing_report",
```

Verify the file contains exactly three insertions of those two lines after the change.

- [ ] **Step 13.2: Smoke-test discovery via the registry**

Run: `python -c "from automana.core.service_modules import SERVICE_MODULES; import importlib; [importlib.import_module(m) for m in SERVICE_MODULES['celery']]; from automana.core.service_registry import ServiceRegistry; print(sorted([k for k in ServiceRegistry._services if k.startswith('ops.integrity.')]))"`

Expected output includes:
```
['ops.integrity.card_catalog_report', 'ops.integrity.mtgstock_report', 'ops.integrity.pricing_report', 'ops.integrity.public_schema_leak', 'ops.integrity.scryfall_integrity', 'ops.integrity.scryfall_run_diff']
```

- [ ] **Step 13.3: Run the full ops test suite**

Run: `pytest tests/unit/core/ -v`
Expected: all green; full sweep ensures the new modules import cleanly under both `backend` and `celery` profiles.

- [ ] **Step 13.4: Commit**

```bash
git add src/automana/core/service_modules.py
git commit -m "feat(metrics): register card_catalog_report + pricing_report in SERVICE_MODULES"
```

---

## Task 14: Beat schedule entries

**Files:**
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 14.1: Add two entries to `beat_schedule`**

In `src/automana/worker/celeryconfig.py`, replace the closing `}` of `beat_schedule` (line 72) with:

```python
    "card-catalog-health-daily": {
        "task": "run_service",
        "schedule": crontab(hour=4, minute=15),  # 04:15 AEST — after the daily ingests
        "kwargs": {"path": "ops.integrity.card_catalog_report"},
    },
    "pricing-health-hourly": {
        "task": "run_service",
        "schedule": crontab(minute=42),  # off-the-hour to avoid Celery cluster
        "kwargs": {"path": "ops.integrity.pricing_report"},
    },
}
```

Note: `celeryconfig.py` sets `timezone = "Australia/Sydney"` (line 49), so crontab values are interpreted in AEST, not UTC. The `task` name `"run_service"` matches the registration in `src/automana/worker/main.py` (`@app.task(name="run_service")`).

- [ ] **Step 14.2: Verify the file parses**

Run: `python -c "import importlib.util, sys; spec = importlib.util.spec_from_file_location('cfg', 'src/automana/worker/celeryconfig.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(sorted(m.beat_schedule.keys()))"`

Expected output:
```
['card-catalog-health-daily', 'daily-analytics-report', 'pricing-health-hourly', 'refresh-mtgjson-daily', 'refresh-mtgstock-daily', 'refresh-scryfall-manifest-nightly']
```

- [ ] **Step 14.3: Commit**

```bash
git add src/automana/worker/celeryconfig.py
git commit -m "feat(metrics): beat schedule for card_catalog (daily) + pricing (hourly) reports"
```

---

## Task 15: Final smoke

**Files:**
- None (verification only)

- [ ] **Step 15.1: Full unit suite**

Run: `pytest tests/unit/core/metrics tests/unit/core/services/ops tests/unit/core/repositories -v`
Expected: every test green; total new test count ≥ 40.

- [ ] **Step 15.2: Verify pipeline-health-check skill picks up the two new runners**

Run the existing skill or its preview: the prompt should now list six `ops.integrity.*` services. (Skill code change is not required — it auto-discovers `ops.integrity.*` keys from `ServiceRegistry`.)

- [ ] **Step 15.3: Optional — invoke a runner via `automana-run` against the dev DB**

Run (from a terminal where `automana-run` is on PATH and the dev DB is reachable):

```bash
automana-run ops.integrity.card_catalog_report
automana-run ops.integrity.pricing_report
```

Expected: each prints a JSON envelope with `check_set`, `total_checks`, `error_count`, `warn_count`, `ok_count`. The `card_catalog.identifier_coverage.scryfall_id` row should show the actual coverage percentage of the dev DB. Real-DB calibration of thresholds (per spec §8 question 1) is not part of this plan — file a follow-up if the initial values produce noisy alerts.

- [ ] **Step 15.4: Final summary commit (no code change — closes the feature)**

If any docs need updating (e.g. `docs/METRICS_REGISTRY.md` to mention the new families exist), do so now in a single small commit:

```bash
git add docs/METRICS_REGISTRY.md  # only if touched
git commit -m "docs(metrics): note card_catalog and pricing metric families"
```

---

## Out of scope (Option C — future plan)

The full operational `db.*` family (vacuum, bloat, connections, TimescaleDB chunks, indexes, locks, WAL, stats freshness) is documented in §9 of the spec and is **not** in this plan. It will need:

- A new `DbStatsRepository` and corresponding `ServiceRegistry.register_db_repository` entry.
- A `pg_monitor` role grant on the role that runs `ops.integrity.db_health_report`.
- Decisions on `pgstattuple` extension availability and primary-only execution for replication metrics.

The 23-metric postgres-pro candidate list from this brainstorm is preserved in the session transcript and should seed that future spec.
