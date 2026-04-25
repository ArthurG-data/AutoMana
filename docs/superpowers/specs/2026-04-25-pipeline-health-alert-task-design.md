# Pipeline Health Alert Task — Design

**Date:** 2026-04-25
**Status:** Spec — pending implementation plan
**Scope:** Cycle 1 of a multi-cycle effort. Defers the DB metrics snapshot (cycle 2) and log/artifact cleanup (cycle 3) to their own specs.

## 1. Motivation

The `ops.integrity.*` service family (Scryfall, MTGStock, public schema leak) gives an authoritative, layer-respecting view of pipeline health, but today it's only invoked on-demand via the `pipeline-health-check` skill on the operator's laptop. Two consequences:

1. Drift goes unnoticed until someone manually runs the check. The current dev DB has been in `❌` for the MTGStock pipeline for at least a day before being surfaced.
2. The skill produces a *full* report every time, which is great for ad-hoc triage but is wrong for a recurring channel post — operators stop reading recurring messages that always say the same thing.

This spec adds a recurring Celery Beat task that runs the integrity services twice daily, persists each run, and posts to Discord **only when the health state of a `check_set` transitions for the worse (or recovers)**.

It also corrects a long-standing timezone bug in the existing Beat schedule, where the inline comments claim `02:00–03:00 AEST` but the cron expressions actually fire at `08:08–11:00 AEST` because `timezone="Australia/Sydney"` interprets the `hour` field as local, not UTC.

## 2. Out of Scope

- **DB metrics time-series snapshot** (cycle 2). The `ops.pipeline_health_snapshot` table introduced here records per-run integrity state — it is *not* the metrics snapshot. The MetricRegistry capture is a separate design.
- **Log / artifact cleanup** (cycle 3).
- **Stuck-run watchdog**. The Scryfall integrity check already detects stuck runs as part of its 24-check suite, and any new failures will surface through the existing alert flow once this spec ships. A dedicated watchdog (more frequent than twice daily, with thresholds in seconds rather than per-run) is left for a later cycle.
- **Auto-remediation**. The task observes and alerts; it does not retry pipelines, kill stuck steps, or rerun integrity services on failure.

## 3. Beat Schedule Fix (precondition)

Current `src/automana/worker/celeryconfig.py` has `timezone = "Australia/Sydney"` and entries like `crontab(hour=8, minute=8)` with the comment `# 02:00 AEST`. The user has confirmed (Q1 of brainstorm): **the comments are correct, the code is wrong**.

Corrected schedule (all times AEST, since `timezone` resolves to Australia/Sydney):

| Entry | Old | New | Comment |
|-------|-----|-----|---------|
| `refresh-scryfall-manifest-nightly` | `hour=8, minute=8` | `hour=2, minute=0` | 02:00 AEST |
| `refresh-mtgjson-daily` | `hour=9, minute=8` | `hour=3, minute=0` | 03:00 AEST |
| `refresh-mtgstock-daily` | `hour=10, minute=8` | `hour=4, minute=0` | 04:00 AEST — runs after MTGJson so reject resolver sees fresh scryfall_id migrations |
| `daily-analytics-report` | `hour=11, minute=0` | `hour=5, minute=0` | 05:00 AEST — after all three pipelines, before AM health check |

Two new entries added in this spec (see §6).

The order `scryfall → mtgjson → mtgstock → analytics` preserves all existing dependency ordering. Analytics moves out of its previously misleading "03:00 AEST" comment slot to a real 05:00 AEST slot — chosen so the AM pipeline health check (06:00 AEST) sees the *post-analytics* state of the system.

## 4. Architecture

Strict adherence to the project's layering: **Beat → Celery task → ServiceManager → Service → Repository → DB**.

```
celery-beat (scheduler)
   │
   ▼
celery-worker
   │  worker.tasks.pipelines.pipeline_health_alert_task
   ▼
ServiceManager.run("ops.health.alert_check", ...)
   │
   ▼
HealthAlertService
   │
   ├── discovers services registered as ops.integrity.*
   ├── invokes each via ServiceManager (sequential, no parallel — DB pool small)
   ├── inserts snapshot rows via PipelineHealthSnapshotRepository
   ├── diffs each new snapshot against the prior snapshot for the same check_set
   └── if any transitions, posts Discord webhook
```

### 4.1 New components

| Component | Path | Responsibility |
|-----------|------|----------------|
| `HealthAlertService` | `src/automana/core/services/ops/health_alert_service.py` | Orchestrates discover → run → persist → diff → alert. Registered as `ops.health.alert_check`. |
| `PipelineHealthSnapshotRepository` | `src/automana/core/repositories/ops/pipeline_health_snapshot_repository.py` | `insert_snapshots(rows)`, `latest_for_check_set(check_set, before_run_id)`. |
| `pipeline_health_alert_task` | `src/automana/worker/tasks/pipelines.py` | Celery task wrapper that calls `ServiceManager.run("ops.health.alert_check")`. |
| Beat entries | `src/automana/worker/celeryconfig.py` | `pipeline-health-am` (06:00 AEST), `pipeline-health-pm` (18:00 AEST). |
| Table DDL | base SQL files under `src/automana/database/SQL/` (exact file determined during planning — `ops` schema definition file) | `ops.pipeline_health_snapshot` table + indexes. |

No migration file. The user has explicitly confirmed (per brainstorm) that the project is still in dev iteration; the dev DB is rebuilt from base SQL via `rebuild_dev_db.sh`. Migrations come back when the project reaches the migration-required stage.

### 4.2 Why a service, not just a Celery task

The CLAUDE.md `Rules` section forbids router→DB access and the architecture doc places all DB I/O behind the service layer. The Celery task is a thin wrapper that exists only to be schedulable — the substance lives in `HealthAlertService` so:

- The same logic is invokable via `automana-run ops.health.alert_check` for ad-hoc runs.
- It's testable in isolation without spinning up Celery.
- It matches `daily_summary_analytics_task`'s shape.

## 5. Data Model

### 5.1 Table: `ops.pipeline_health_snapshot`

| column | type | constraints | notes |
|--------|------|-------------|-------|
| `id` | `bigserial` | `PRIMARY KEY` | |
| `run_id` | `uuid` | `NOT NULL` | groups all check_sets from a single task invocation |
| `captured_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `check_set` | `text` | `NOT NULL` | matches the `check_set` field in the integrity report envelope, e.g. `scryfall_integrity` |
| `pipeline` | `text` | `NOT NULL` | derived: `scryfall`, `mtgstock`, `infrastructure`, etc. |
| `status` | `text` | `NOT NULL`, `CHECK status IN ('ok','warn','error')` | derived from counts (see §5.2) |
| `error_count` | `int` | `NOT NULL` | from report envelope |
| `warn_count` | `int` | `NOT NULL` | from report envelope |
| `total_checks` | `int` | `NOT NULL` | from report envelope |
| `report` | `jsonb` | `NOT NULL` | full envelope for forensics |

Indexes:
- `(check_set, captured_at DESC)` — supports "fetch the last snapshot for this check_set before run X"
- `(run_id)` — supports "all check_sets for a single run"

### 5.2 Status derivation

```
status =
  'error' if error_count > 0
  'warn'  if error_count == 0 and warn_count > 0
  'ok'    otherwise
```

This matches the icon rules used by the existing `pipeline-health-check` skill.

### 5.3 Pipeline derivation

Strip the `check_set` of any pipeline-source prefix:

| `check_set` | `pipeline` |
|-------------|-----------|
| `scryfall_integrity` | `scryfall` |
| `scryfall_run_diff` | `scryfall` |
| `mtgstock_report` | `mtgstock` |
| `mtgjson_*` (future) | `mtgjson` |
| `public_schema_leak` | `infrastructure` |

The mapping rule: take the substring before the first `_`; if it matches a known pipeline name (scryfall / mtgjson / mtgstock), use it; otherwise group as `infrastructure`. The known-pipeline list is enumerated from the celery beat panel registration grep used by the skill, falling back to `infrastructure` when a check_set's prefix is unknown — so a future `vendor_x_audit` check_set lands in `infrastructure` until a mapping is added.

## 6. Beat Schedule — Final State

```python
beat_schedule = {
    "refresh-scryfall-manifest-nightly": {
        "task": "automana.worker.tasks.pipelines.daily_scryfall_data_pipeline",
        "schedule": crontab(hour=2, minute=0),  # 02:00 AEST
    },
    "refresh-mtgjson-daily": {
        "task": "automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline",
        "schedule": crontab(hour=3, minute=0),  # 03:00 AEST
    },
    "refresh-mtgstock-daily": {
        "task": "automana.worker.tasks.pipelines.mtgStock_download_pipeline",
        "schedule": crontab(hour=4, minute=0),  # 04:00 AEST — after Scryfall (reject resolver) and MTGJson
    },
    "daily-analytics-report": {
        "task": "automana.worker.tasks.analytics.daily_summary_analytics_task",
        "schedule": crontab(hour=5, minute=0),  # 05:00 AEST — after all data pipelines
    },
    "pipeline-health-am": {
        "task": "automana.worker.tasks.pipelines.pipeline_health_alert_task",
        "schedule": crontab(hour=6, minute=0),  # 06:00 AEST — post-pipeline health
    },
    "pipeline-health-pm": {
        "task": "automana.worker.tasks.pipelines.pipeline_health_alert_task",
        "schedule": crontab(hour=18, minute=0),  # 18:00 AEST — same-day insurance
    },
}
```

## 7. Service Flow

`HealthAlertService.run()` performs, in order:

1. **Generate `run_id`** — `uuid.uuid4()`.
2. **Discover** — query `ServiceManager` for all registered services whose key starts with `ops.integrity.`. Sort alphabetically for determinism.
3. **Run each** — sequentially:
    - On success: parse the report envelope, build a snapshot row.
    - On exception: build a synthetic snapshot row with `status='error'`, `error_count=1`, `warn_count=0`, `total_checks=0`, `report={"exception": "<traceback>", "check_set": "<service_key>"}`. The traceback is captured so a broken *integrity service* surfaces as a transition rather than silently zeroing out.
4. **Persist** — insert all snapshot rows in one batch via `PipelineHealthSnapshotRepository.insert_snapshots(rows)`.
5. **Diff** — for each new row, fetch the most recent prior row for that `check_set` excluding the rows just inserted in this run (`WHERE check_set = ? AND run_id != <current_run_id> ORDER BY captured_at DESC LIMIT 1`):
    - No prior row → classify as `baseline` (silent).
    - `status` unchanged → `unchanged` (silent).
    - Status transition `ok→warn`, `ok→error`, `warn→error` → `degraded`.
    - Status transition `error→warn`, `error→ok`, `warn→ok` → `recovered`.
6. **Alert** — if any `degraded` or `recovered` classifications exist, build the transition-focused Discord payload (§8), POST it. Otherwise no-op.
7. **Return**:
   ```python
   {
     "run_id": "<uuid>",
     "total_check_sets": int,
     "degraded": [{"check_set", "from_status", "to_status", "delta_summary"}, ...],
     "recovered": [{"check_set", "from_status", "to_status"}, ...],
     "baselines": [check_set, ...],
     "alerted": bool,
   }
   ```

## 8. Discord Payload

Transition-focused (option A from brainstorm Q4). Two example outputs:

**Degradation:**
```
⚠️ Pipeline health degraded — 2026-04-25 06:00 AEST
· mtgstock: ✅ → ❌ (10 new errors, top: pricing.stg_price_observation_reject does not exist)
· scryfall.integrity: ✅ → ⚠️ (3 new warnings)
```

**Recovery:**
```
✅ Pipeline health recovered — 2026-04-25 18:00 AEST
· mtgstock: ❌ → ✅ (10 errors resolved)
```

**Mixed run** (rare but possible):
```
⚠️ Pipeline health changed — 2026-04-25 06:00 AEST
Degraded:
· scryfall.integrity: ✅ → ❌ (1 new error)
Recovered:
· mtgstock: ❌ → ⚠️ (warnings only)
```

Each line shows the `check_set` (with the `pipeline.` prefix dropped if redundant), the icon transition, and a one-line delta. The delta for `degraded` includes the top error's `check_name` and a 60-char-truncated `details` string. Discord 2000-char limit handled by truncating to top-5 transitions and appending `… and N more (run_id=<uuid>)`.

Webhook hygiene per the existing skill: read via `get_settings().DISCORD_WEBHOOK_URL`, never logged, posted via the standard service HTTP client.

## 9. Failure Handling

| Failure | Behavior |
|---------|----------|
| Single integrity service raises | Synthetic `status=error` snapshot row written; participates in diff like any other transition. The exception traceback lands in `report.exception`. |
| All integrity services raise | Each gets its own synthetic row. The diff sees N transitions; one Discord post lists them all. |
| Webhook URL unset | Service logs a `WARNING` and returns `alerted=false`. Snapshot rows still written. Not an error condition — local dev environments don't need a webhook. |
| Discord POST returns non-2xx | Service logs the status code and response body, returns `alerted=false`. No retry — Discord rate-limits with `retry_after`, and twice-daily cadence means the next run will surface the issue if it persists. |
| DB unavailable | Task raises. Per project rules, pipeline tasks don't `autoretry_for` — Celery's default (no retry) applies. Failure surfaces in the standard logging stack and Celery's flower/result UI. |
| Existing prior snapshot row is corrupted (e.g. unparseable JSON) | Diff treats it as a missing prior → baseline classification. Logged as `WARNING`. |

## 10. Testing Strategy

### 10.1 Unit
- Pure-function diff (`classify(prev_snapshot, new_snapshot) -> Literal["baseline","unchanged","degraded","recovered"]`). All six transition cases plus baseline plus equal-status.
- Status derivation from counts (3 cases).
- Pipeline derivation from check_set (5+ cases including unknown prefix → `infrastructure`).
- Discord payload formatter with mixed degraded/recovered, single-item, empty (asserts no payload built), >5-item truncation.

### 10.2 Service-level
- Stubbed `ServiceManager` yielding canned integrity reports.
- Stubbed Discord HTTP client.
- Real DB via the existing test DB fixture.
- Asserts: snapshot rows inserted with correct shape; second invocation with identical canned reports produces no Discord call; injected report change triggers exactly one Discord call with the expected payload.
- Service exception path: stub one integrity service to raise → assert synthetic error row written, traceback in `report.exception`.

### 10.3 Integration
- Real Postgres (dev DB), real `ServiceManager`, mocked Discord client.
- Run the service end-to-end → verify a row exists for every `ops.integrity.*` service registered at the time of the test.
- Run twice → second run produces no transitions, no alert call.
- Manually flip a snapshot row's `status` in the DB between calls → third run alerts.

Discord is **always mocked** in tests. The real webhook is never hit from CI or the test suite.

## 11. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Pipeline failure floods Discord with daily error growth (e.g. mtgstock keeps adding new errors) | Diff is on `status`, not `error_count`. A pipeline stuck at `error` stays silent. Only a transition triggers alerts. |
| Future integrity service uses a check_set name that doesn't fit the pipeline-prefix mapping | Falls through to `pipeline='infrastructure'`. Rule documented in §5.3. |
| Two scheduled runs collide (e.g. operator manually triggers the task during the AM window) | Each invocation gets its own `run_id`. The diff fetches the latest snapshot strictly older than the current run via `captured_at`. Worst case: two near-simultaneous runs each treat the other as the baseline; one might miss a transition. Acceptable — twice-daily cadence makes this extremely rare and the next scheduled run resolves it. |
| Snapshot table grows unboundedly | Cycle 3 (cleanup) will add retention. Until then, twice-daily × ~5 check_sets = ~3,650 rows/year. Negligible. |
| The integrity services themselves become slow | Sequential execution + small DB pool means total service runtime is bounded by the slowest check. Currently ~5–10 seconds total. Documented as expected; no timeout enforced at this layer. |

## 12. Open Questions

None at spec time. All clarifying questions from the brainstorm are resolved:

- Q1 (timezone intent) → A — comments are right, code is wrong; fix code.
- Q2 (snapshot storage) → B — Postgres.
- Q3 (frequency) → B — twice daily, 06:00 + 18:00 AEST.
- Q4 (alert format) → A — transition-focused.
- Migration policy → no migration; add to base SQL files.
