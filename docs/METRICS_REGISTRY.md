# MetricRegistry and Sanity Reports

`src/automana/core/metrics/` houses the `MetricRegistry` — a decorator-based registry for sanity-report metrics, parallel in structure to `ServiceRegistry`. Each metric is an async function that queries a small, well-defined slice of the DB and returns a `MetricResult`. Runner services pick a subset and wrap the results in the same integrity-report envelope used across all `ops.integrity.*` services.

---

## Core types

All types are exported from `automana.core.metrics`:

```python
from automana.core.metrics import MetricRegistry, MetricResult, MetricConfig, Severity, Threshold
```

### `Severity`

```python
class Severity(str, Enum):
    OK   = "ok"
    WARN = "warn"
    ERROR = "error"
```

### `Threshold`

A declarative severity rule for numeric metrics. Frozen dataclass.

```python
@dataclass(frozen=True)
class Threshold:
    warn:      float
    error:     float
    direction: Literal["lower_is_worse", "higher_is_worse"] = "higher_is_worse"
```

`Threshold.evaluate(value)` returns:

- `Severity.WARN` when `value` is `None` (data missing is treated as a warning, not silence).
- For `higher_is_worse`: `ERROR` if `value >= error`, `WARN` if `value >= warn`, else `OK`.
- For `lower_is_worse`: `ERROR` if `value <= error`, `WARN` if `value <= warn`, else `OK`.

Note: for `lower_is_worse` thresholds the `error` bound is the tighter (lower) number. Example: `Threshold(warn=95, error=80, direction="lower_is_worse")` fires ERROR when the value drops to 80 or below and WARN when it drops to 95 or below.

### Callable severity

Use `Callable[[Any], Severity]` only for non-numeric cases where a `Threshold` does not make sense — for example, matching a status string:

```python
def _status_severity(value: str | None) -> Severity:
    if value in ("success",):
        return Severity.OK
    if value in ("partial", "running", "pending"):
        return Severity.WARN
    return Severity.ERROR  # 'failed' or unknown
```

Prefer `Threshold` for every numeric metric. It is introspectable, JSON-serializable, and keeps the comparison semantics next to the threshold values rather than buried in a lambda.

### `MetricResult`

The contract every metric function must return. Frozen dataclass.

```python
@dataclass(frozen=True)
class MetricResult:
    row_count: int | float | str | None
    details:   dict[str, Any] = field(default_factory=dict)
```

`row_count` is the headline scalar rendered in the report envelope and passed to the severity rule. `details` is a free-form JSON-serializable dict for whatever context is useful to the operator (per-step breakdown, raw counts behind a ratio, etc.).

### `MetricConfig`

Stored in the registry per metric. Holds `path`, `category`, `description`, `severity`, `db_repositories`, `module`, `function`. You do not construct this manually — `@MetricRegistry.register(...)` creates it.

---

## `MetricRegistry` API

### `@MetricRegistry.register(...)`

Decorator that registers a metric function at import time.

```python
@MetricRegistry.register(
    path="mygroup.metric_name",
    category="health",           # one of: "health" | "volume" | "timing" | "status"
    description="Human-readable one-liner for the report envelope.",
    severity=Threshold(warn=5_000, error=50_000, direction="higher_is_worse"),
    db_repositories=["price"],   # repository names the runner will inject
)
async def metric_name(price_repository: PriceRepository, ingestion_run_id: int | None = None) -> MetricResult:
    ...
```

`severity=None` is valid — the metric always evaluates to `OK` (informational, no pass/fail).

Valid categories: `"health"`, `"volume"`, `"timing"`, `"status"`. An unknown category raises `ValueError` at registration time.

### `MetricRegistry.get(path)`

Returns a `MetricConfig` or `None`.

### `MetricRegistry.all_metrics()`

Returns a `dict[str, MetricConfig]` snapshot of the full registry.

### `MetricRegistry.select(names=None, category=None, prefix=None)`

Returns a list of `MetricConfig` sorted by path. All supplied filters must match (AND semantics).

```python
# everything under the mtgstock prefix
MetricRegistry.select(prefix="mtgstock.")

# only health metrics in the mtgstock group
MetricRegistry.select(prefix="mtgstock.", category="health")

# two specific metrics by path
MetricRegistry.select(names=["mtgstock.link_rate_pct", "mtgstock.run_status"])
```

An unknown `category` string raises `ValueError`.

### `MetricRegistry.evaluate(config, value)`

Applies `config.severity` to `value` and returns a `Severity`. Safe to call with `value=None`.

### `MetricRegistry.clear()`

Wipes the registry. **Tests only** — never call from production code.

---

## How auto-registration works

Metrics register themselves via `@MetricRegistry.register(...)` at module import time, the same side-effect pattern used by `@ServiceRegistry.register(...)`.

For a group of metrics to be available, their modules must be imported before `MetricRegistry.select()` is called. The conventional pattern is a package `__init__.py` that imports all sibling modules:

```python
# src/automana/core/metrics/mtgstock/__init__.py
from automana.core.metrics.mtgstock import run_metrics      # noqa: F401
from automana.core.metrics.mtgstock import staging_metrics  # noqa: F401
from automana.core.metrics.mtgstock import promotion_metrics  # noqa: F401
```

The runner service then imports the package at the top of its module:

```python
import automana.core.metrics.mtgstock  # noqa: F401  — triggers registration of all mtgstock.* metrics
```

Because the runner service itself is listed in `SERVICE_MODULES` (loaded at `ServiceManager` boot), the metrics are registered before any call to `MetricRegistry.select()` is made.

---

## How the runner service dispatches

`ops.integrity.mtgstock_report` (in `src/automana/core/services/ops/mtgstock_report.py`) is the reference runner. Its dispatch loop:

1. Calls `MetricRegistry.select(names=..., category=..., prefix="mtgstock.")` to build the filtered list.
2. For each `MetricConfig`, resolves the metric function via `importlib.import_module(config.module)` + `getattr(module, config.function)`.
3. Builds a `candidate_kwargs` dict of every injectable value (`price_repository`, `ops_repository`, `ingestion_run_id`), then uses `inspect.signature` to filter to only the kwargs the metric's signature accepts — the same pattern `run_service` uses.
4. Catches any exception from a metric invocation and converts it to an `error`-severity row rather than aborting the report. One misbehaving metric does not take the whole report down.
5. Calls `MetricRegistry.evaluate(config, result.row_count)` for each result.
6. Passes all rows to `_build_report` (from `core/services/ops/integrity_checks.py`) which partitions them into `errors`, `warnings`, `passed`, and returns the standard envelope.

The standard envelope shape:

```python
{
    "check_set":    str,   # identifies which report ran
    "total_checks": int,
    "error_count":  int,
    "warn_count":   int,
    "ok_count":     int,
    "errors":       list[dict],   # rows with severity == "error"
    "warnings":     list[dict],   # rows with severity == "warn"
    "passed":       list[dict],   # rows with severity == "ok"
    "rows":         list[dict],   # all rows
}
```

Each row: `{"check_name": str, "severity": str, "row_count": ..., "details": dict}`.

---

## Walkthrough — adding a metric

This section walks through `mtgstock.link_rate_pct` as a concrete example of the full registration lifecycle.

**1. Choose the module.** Staging-table metrics live in `src/automana/core/metrics/mtgstock/staging_metrics.py`. Create a new file or add to an existing one based on logical grouping.

**2. Write the function.**

```python
@MetricRegistry.register(
    path="mtgstock.link_rate_pct",
    category="health",
    description="% of staged rows (linked + rejected) that resolved to a card_version_id.",
    severity=Threshold(warn=95, error=80, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def link_rate_pct(
    price_repository: PriceRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    linked   = await price_repository.fetch_linked_count()
    rejected = await price_repository.fetch_rejected_count()
    denom    = linked + rejected

    rate = round(100.0 * linked / denom, 2) if denom else None
    return MetricResult(
        row_count=rate,
        details={"linked": linked, "rejected": rejected, "denominator": denom},
    )
```

Key points:
- `severity=Threshold(warn=95, error=80, direction="lower_is_worse")` — a link rate below 95 % is a warning; below 80 % is an error.
- When `denom` is zero, `rate` is `None`. `Threshold.evaluate(None)` returns `Severity.WARN` — so a completely empty staging table is flagged rather than silently passing.
- `ingestion_run_id` is accepted but unused here because `stg_price_observation` has no run column. The parameter is included for API uniformity — the runner always passes it.
- `details` carries the raw counts so the operator can see `linked` and `rejected` without re-querying.

**3. Ensure the module is imported.** Add it to the package `__init__.py` if not already there:

```python
from automana.core.metrics.mtgstock import staging_metrics  # noqa: F401
```

**4. Verify registration.** After importing the package, `MetricRegistry.get("mtgstock.link_rate_pct")` should return the `MetricConfig`.

**5. Add repository methods if needed.** Each `db_repositories` name must correspond to a repository the runner service already injects. For a new group (not `mtgstock`), you may need to add repository entries to `ServiceRegistry` and declare them in `@ServiceRegistry.register(db_repositories=[...])` on the runner.

**6. Write tests.** See `tests/unit/core/metrics/mtgstock/test_staging_metrics.py` for the pattern: mock the repository, call the function directly, assert `result.row_count` and `result.details`.

---

## Adding a new metric group (new pipeline)

To add a metric group for a different pipeline (e.g., `scryfall.*`):

1. Create `src/automana/core/metrics/<pipeline>/` with an `__init__.py` that imports all sibling modules.
2. Write metric modules following the same pattern.
3. Create a runner service in `src/automana/core/services/ops/<pipeline>_report.py` that:
   - Imports `automana.core.metrics.<pipeline>` to trigger registration.
   - Calls `MetricRegistry.select(prefix="<pipeline>.")`.
   - Uses the `_invoke_metric` + `_build_report` pattern from `mtgstock_report.py`.
   - Registers with `@ServiceRegistry.register("ops.integrity.<pipeline>_report", db_repositories=[...])`.
4. Add the runner module to `SERVICE_MODULES` in `core/service_modules.py` for every applicable namespace.

---

## Related docs

- [`docs/MTGSTOCK_PIPELINE.md`](MTGSTOCK_PIPELINE.md) — the first pipeline using this registry; metric table and CLI reference
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — layer overview including `core/metrics/`
- [`docs/DESIGN_PATTERNS.md`](DESIGN_PATTERNS.md) — design patterns lexicon
