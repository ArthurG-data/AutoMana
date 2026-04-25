# Database Health Metrics — Design Spec

**Date:** 2026-04-25
**Author:** brainstormed with `postgres-pro` and `data-analyst` candidate-list passes
**Status:** Draft — awaiting user review
**Scope (this spec):** Medium — `card_catalog.*` and `pricing.*` metric families
**Deferred (Option C — future spec):** `db.*` operational metrics (vacuum, bloat, connections, TimescaleDB chunks, indexes, locks, WAL, stats freshness). Requires a new `DbStatsRepository` and a `pg_monitor` role grant. Tracked separately because it crosses the data-shape / DB-infra boundary.

---

## 1. Motivation

The pipeline-health-check skill recently surfaced that 113,776 `card_version` rows had no `scryfall_id` row in `card_catalog.card_external_identifier`, because `card_catalog.card_identifier_ref` was empty and the JOIN in `insert_full_card_version` silently produced zero rows. Commit `0d69501` shipped the seed + a `register_external_identifier` service, but no metric existed to detect this class of slow-rot before it accumulated to 113k rows.

This spec adds two metric families to the existing `MetricRegistry` to catch this and similar data-shape drifts:

- **`card_catalog.*`** — identifier coverage per source, orphan unique_cards, collision detection.
- **`pricing.*`** — price freshness per source, FK soft-integrity, staging drain, duplicate detection.

Both families follow the existing `mtgstock.*` pattern documented in `docs/METRICS_REGISTRY.md` exactly: per-family package under `core/metrics/<family>/`, runner service under `core/services/ops/<family>_report.py`, registered with `@ServiceRegistry.register("ops.integrity.<family>_report", ...)`.

The `pipeline-health-check` skill auto-discovers `ops.integrity.*` services, so the new runners will appear in the health report automatically — no skill edits.

---

## 2. Architecture

### 2.1 Module map

```
src/automana/core/metrics/
    card_catalog/                          # NEW
        __init__.py                        # imports all sibling modules
        identifier_metrics.py              # 6 identifier-coverage + collision metrics
        catalog_metrics.py                 # orphan_unique_cards
    pricing/                               # NEW
        __init__.py
        freshness_metrics.py               # max age, per-source lag
        coverage_metrics.py                # per-source observation coverage
        integrity_metrics.py               # FK soft-integrity, duplicates, staging drain

src/automana/core/services/ops/
    card_catalog_report.py                 # NEW — runner
    pricing_report.py                      # NEW — runner

src/automana/core/repositories/
    card_catalog/card_repository.py        # ADD methods to CardReferenceRepository (see §4.1)
    app_integration/mtg_stock/price_repository.py  # ADD methods (see §4.2)
    ops/ops_repository.py                  # ADD method: latest_run_ended_at(pipeline_name)

src/automana/core/service_modules.py       # register both new runner modules

tests/unit/core/metrics/
    card_catalog/                          # NEW
        test_identifier_metrics.py
        test_catalog_metrics.py
    pricing/                               # NEW
        test_freshness_metrics.py
        test_coverage_metrics.py
        test_integrity_metrics.py
tests/unit/core/services/ops/
    test_card_catalog_report.py            # NEW
    test_pricing_report.py                 # NEW
```

### 2.2 Layering

The new code touches three layers, all already-existing:

- **Metric layer** (`core/metrics/<family>/*.py`) — pure functions decorated with `@MetricRegistry.register(...)`, returning `MetricResult`. Take repositories as kwargs; the runner injects them.
- **Repository layer** — new SELECT-only methods on `CardRepository`, `PriceRepository`, `OpsRepository`. Pure SQL, no business logic.
- **Service layer** (`core/services/ops/<family>_report.py`) — the runner: re-uses `_invoke_metric` + `_build_report` patterns from `mtgstock_report.py` verbatim. Two near-identical files; see §6 on whether to extract a shared helper.

No router changes — these services are run via Celery beat (see §7) and `automana-run` CLI, same as `ops.integrity.mtgstock_report` and `ops.integrity.scryfall_integrity`.

### 2.3 Data dependencies

All metrics are read-only SELECT workloads. They touch:

| Schema | Tables read |
|---|---|
| `card_catalog` | `card_version`, `card_external_identifier`, `card_identifier_ref`, `unique_cards_ref` |
| `pricing` | `price_observation`, `source_product`, `product_ref`, `mtg_card_products`, `stg_price_observation` |
| `ops` | `ingestion_runs` (new method needed: latest successful `ended_at` per pipeline) |

No schema changes. No new extensions. No new role grants. (The `pg_monitor` requirement is deferred-Option-C territory.)

---

## 3. Metric inventory

Total: **15 metrics across two families.** Numbers are starting thresholds; they are intentionally generous so the first runs surface real signal before being tightened on a per-source basis.

### 3.1 `card_catalog.*` — 8 metrics

| Path | Category | Severity | Why |
|---|---|---|---|
| `card_catalog.identifier_coverage.scryfall_id` | health | `Threshold(warn=99, error=95, lower_is_worse)` | Headline — would have caught the 113k incident. Scryfall is the primary catalogue; coverage should be ~100%. |
| `card_catalog.identifier_coverage.oracle_id` | health | `Threshold(warn=99, error=95, lower_is_worse)` | Oracle ID is the abstract-card identifier; near-100% expected. Stored on `card_version` per existing schema. |
| `card_catalog.identifier_coverage.tcgplayer_id` | health | `Threshold(warn=80, error=60, lower_is_worse)` | Major pricing source; gaps block price-join paths. Lower threshold reflects regional/promo cards lacking TCGPlayer listings. |
| `card_catalog.identifier_coverage.cardmarket_id` | health | `Threshold(warn=70, error=50, lower_is_worse)` | Regional source; coverage naturally lower than scryfall. |
| `card_catalog.identifier_coverage.multiverse_id` | volume | `None` (informational) | Deprecated identifier; track count for change detection. No threshold — historical baseline only. |
| `card_catalog.identifier_coverage.tcgplayer_etched_id` | volume | `None` (informational) | Only etched printings carry this; coverage is naturally a tiny subset. Track for drift, not pass/fail. |
| `card_catalog.print_coverage.orphan_unique_cards` | health | `Threshold(warn=5, error=50, higher_is_worse)` | `unique_cards_ref` rows with zero `card_version` children. Small counts benign (tokens), large counts = mid-run set-ingest stall. |
| `card_catalog.duplicate_detection.external_id_value_collision` | health | `Threshold(warn=1, error=1, higher_is_worse)` | `(card_identifier_ref_id, value)` should be UNIQUE. Any non-zero count = constraint bypass or replication desync. |

**Identifier-coverage formula (uniform across all six):**

```sql
SELECT 100.0 * COUNT(DISTINCT cei.card_version_id) / NULLIF(COUNT(*) OVER (), 0)
FROM card_catalog.card_version cv
LEFT JOIN card_catalog.card_external_identifier cei
       ON cei.card_version_id = cv.card_version_id
LEFT JOIN card_catalog.card_identifier_ref cir
       ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
      AND cir.identifier_name = $1
```

(Implementation will use a single `CardRepository.fetch_identifier_coverage_pct(name: str) -> float | None` method, called from each metric with its name. The two informational ones — multiverse_id, tcgplayer_etched_id — return raw COUNT, not a pct.)

`details` for each coverage metric: `{"identifier_name": str, "covered": int, "total": int}` so the operator can see the raw counts behind the percentage.

### 3.2 `pricing.*` — 7 metrics

| Path | Category | Severity | Why |
|---|---|---|---|
| `pricing.freshness.price_observation_max_age_days` | timing | `Threshold(warn=2, error=7, higher_is_worse)` | Days since the most recent `price_observation.ts_date`. Daily ingests should produce same/next-day rows. |
| `pricing.freshness.max_per_source_lag_hours` | timing | `Threshold(warn=48, error=120, higher_is_worse)` | Hours since the latest successful run *per source*. Headline = MAX across sources; `details` carries the per-source breakdown. Catches one source stalling while others run. |
| `pricing.coverage.min_per_source_observation_coverage_pct` | health | `Threshold(warn=50, error=20, lower_is_worse)` | Per source, fraction of `source_product` rows with a `price_observation` in last 30d. Headline = MIN; `details` per-source. |
| `pricing.referential.product_without_mtg_card_products` | health | `Threshold(warn=5, error=20, higher_is_worse)` | `pricing.product_ref` rows whose `game_id` matches the `mtg` row in `pricing.card_game` but have no `pricing.mtg_card_products` row — orphans from partial promotion. |
| `pricing.referential.observation_without_source_product` | health | `Threshold(warn=1, error=10, higher_is_worse)` | `price_observation` rows whose `source_product_id` no longer exists. Hard FK should make this 0; non-zero means schema corruption. |
| `pricing.staging.stg_price_observation_residual_count` | volume | `Threshold(warn=1_000_000, error=5_000_000, higher_is_worse)` | `stg_price_observation` should drain to ~0 between runs. Sustained large counts = stage 3 failed to drain. |
| `pricing.duplicate_detection.observation_duplicates_on_pk` | health | `Threshold(warn=1, error=1, higher_is_worse)` | Composite PK should make duplicates impossible; any count = index corruption. |

`details` keys vary; per-source breakdowns include `{"per_source": {source_code: value}}`. Freshness metrics include `{"as_of": ISO timestamp}` so reports are self-dating.

---

## 4. Repository methods

### 4.1 `CardReferenceRepository` (`src/automana/core/repositories/card_catalog/card_repository.py`)

The repository is registered in `ServiceRegistry` under the name `"card"` and maps to class `CardReferenceRepository`. New methods are added to that class.


```python
async def fetch_identifier_coverage_pct(self, identifier_name: str) -> dict | None:
    """Return {'covered': int, 'total': int, 'pct': float|None} for one identifier name.
    Returns None if total is 0 (caller treats as WARN per Threshold semantics)."""

async def fetch_identifier_value_count(self, identifier_name: str) -> int:
    """COUNT of card_version rows that have at least one row for `identifier_name`.
    For the informational metrics (multiverse_id, tcgplayer_etched_id)."""

async def fetch_orphan_unique_cards_count(self) -> int:
    """COUNT of unique_cards_ref with zero card_version children."""

async def fetch_external_id_value_collisions(self) -> int:
    """COUNT of (card_identifier_ref_id, value) tuples appearing more than once."""
```

### 4.2 `PriceRepository` (`src/automana/core/repositories/app_integration/mtg_stock/price_repository.py`)

> Note: this repository's path lives under `mtg_stock/` for historical reasons. The new methods are pricing-domain-wide, not mtg_stock-specific. Renaming/relocating the repository is **out of scope** for this spec — flagged for future cleanup.

```python
async def fetch_max_observation_age_days(self) -> int | None:
    """Days since the most recent price_observation.ts_date across all sources."""

async def fetch_per_source_lag_hours(self) -> dict[str, float | None]:
    """{source_code: hours_since_latest_observation} for every source in price_source."""

async def fetch_per_source_observation_coverage_pct(
    self, window_days: int = 30
) -> dict[str, float | None]:
    """{source_code: pct} where pct = source_products with an observation in window / source_products total."""

async def fetch_orphan_product_ref_mtg_count(self) -> int:
    """product_ref rows with game_id=mtg but no mtg_card_products row."""

async def fetch_orphan_observation_count(self) -> int:
    """price_observation rows with source_product_id not in source_product."""

async def fetch_stg_residual_count(self) -> int:
    """Estimated row count of stg_price_observation via pg_class.reltuples."""

async def fetch_observation_pk_collision_count(self) -> int:
    """Composite-PK violations in price_observation (should always be 0)."""
```

### 4.3 `OpsRepository` (`src/automana/core/repositories/ops/ops_repository.py`)

```python
async def fetch_latest_successful_run_ended_at(self, pipeline_name: str) -> datetime | None:
    """ended_at of the most recent ingestion_runs row with status='success' for the given pipeline."""
```

This is consumed indirectly by `pricing.freshness.max_per_source_lag_hours`, which iterates over the known pricing pipelines (`mtg_stock_all`, `mtgjson_daily`) and computes per-source lag.

---

## 5. Runner services

Two new runners, structurally identical to `ops.integrity.mtgstock_report`.

### 5.1 `ops.integrity.card_catalog_report`

```python
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
    ...
```

`ingestion_run_id` is **not** a parameter — these metrics are about steady-state DB shape, not pipeline-run-scoped.

### 5.2 `ops.integrity.pricing_report`

```python
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
    ...
```

Same omission of `ingestion_run_id`.

### 5.3 Shared helper question

`mtgstock_report.py` already has `_normalize_names`, `_resolve_metric_function`, `_invoke_metric`, `_result_to_row`. Two more runner files would copy these with minor signature changes.

**Decision: extract to `core/services/ops/_metric_runner.py` as part of this spec.** Three runners is the threshold where DRY pays off. The helper exposes:

```python
async def run_metric_report(
    *,
    check_set: str,
    prefix: str,
    metrics: str | list[str] | None,
    category: str | None,
    repositories: dict[str, Any],         # name -> repo instance
    extra_kwargs: dict[str, Any] | None = None,
) -> dict:
    ...
```

The existing `mtgstock_report` will be migrated to use this helper as part of this PR (single, low-risk refactor).

---

## 6. Beat schedule

Add two entries to `core/celery_app.py` beat schedule:

```python
"card-catalog-health-daily": {
    "task": "automana.worker.tasks.run_service",
    "schedule": crontab(hour=4, minute=15),  # after mtgjson_daily
    "kwargs": {"service_name": "ops.integrity.card_catalog_report"},
},
"pricing-health-hourly": {
    "task": "automana.worker.tasks.run_service",
    "schedule": crontab(minute=42),
    "kwargs": {"service_name": "ops.integrity.pricing_report"},
},
```

Rationale:
- `card_catalog_report` runs once daily at 04:15, after the daily ingests have completed; data shape is slow-changing.
- `pricing_report` runs hourly because pricing freshness can degrade fast (a stalled cron is a 1h-resolution problem, not a 24h one). The hour offset (`:42`) avoids the on-the-hour Celery cluster.

The reports write structured logs (the runner already does); a follow-up PR can wire them to Discord via the `pipeline-health-check` rendering path.

---

## 7. Testing strategy

Per `tests/unit/core/metrics/mtgstock/test_*` pattern: mock the repository, call the metric function directly, assert `result.row_count` and `result.details`.

**Per metric: 3 cases minimum**
- Healthy value → expected row_count, expected details
- Warn/Error boundary value → severity transitions correctly when re-evaluated via `MetricRegistry.evaluate`
- Empty / `None` denominator → returns `None` row_count without raising

**Per runner: 4 cases**
- All metrics succeed → standard envelope, correct counts
- One metric raises → envelope still returned, raising metric appears as ERROR-severity row with `exception` detail (matches existing `mtgstock_report` behavior)
- Filter by `category="health"` → only health metrics run
- Filter by explicit `metrics="card_catalog.identifier_coverage.scryfall_id"` → only that metric runs

**Per repository method: 1-2 integration tests** against the test database harness from the integration test plan (commit `7558a83`). These confirm SQL is valid; metric-level tests use mocks.

Coverage target: 90% (per `fox-unit-tester` standard).

---

## 8. Open decisions for user review

1. **Beat cadence** — daily for `card_catalog`, hourly for `pricing`. OK or different?
2. **Discord integration** — included in this spec or follow-up PR? Default: follow-up.
3. **Per-source threshold overrides** — should `pricing.coverage.min_per_source_observation_coverage_pct` allow per-source thresholds (e.g., tcg=85, cardmarket=70), or is the MIN-headline + per-source-details enough? Default: MIN-headline for v1; per-source overrides if/when the registry grows that feature.
4. **Repository relocation** — leave `PriceRepository` under `app_integration/mtg_stock/` or move to `pricing/`? Default: leave; flag as future cleanup.
5. **Helper extraction** — extract `_metric_runner.py` and migrate `mtgstock_report` in this PR? Default: yes.

---

## 9. Out of scope (deferred to Option C)

The full postgres-pro candidate list — vacuum, bloat, connections, TimescaleDB chunk health, indexes (unused / FK-missing), locks, long-running queries, replication/WAL slot, stats freshness, disk size — will land in a separate spec. It needs:

- A new `DbStatsRepository` that queries `pg_catalog`, `pg_stat_*`, `timescaledb_information.*`.
- A `pg_monitor` role grant (or equivalent) on the role that runs `ops.integrity.db_health_report`. Current role-per-schema design doesn't grant this.
- A decision on whether to require `pgstattuple` for exact bloat measurement or stick with `pg_stat_user_tables` approximations.
- A decision on whether the runner runs on the primary only (replication metrics need this) or on any node.

The 23-metric postgres-pro candidate list from this brainstorm is preserved in the agent transcript for the future spec.
