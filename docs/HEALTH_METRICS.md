# Database Health Metrics

Two metric families on top of the existing `MetricRegistry` surface data-shape drift across the card catalog and pricing schemas. They were introduced after a `pipeline-health-check` run uncovered 113,776 `card_version` rows missing a `scryfall_id` row in `card_external_identifier` — a class of slow-rot that no integrity check or pipeline log was catching.

For the registry mechanics (decorator, severity, runner dispatch) see [`METRICS_REGISTRY.md`](METRICS_REGISTRY.md). This doc covers the metrics themselves and how to run the reports.

---

## At a glance

| Family | Runner service | Beat schedule | What it watches |
|---|---|---|---|
| `card_catalog.*` | `ops.integrity.card_catalog_report` | `card-catalog-health-daily` (04:15 AEST) | Identifier coverage per source, orphan unique cards, external-id collisions |
| `pricing.*`      | `ops.integrity.pricing_report`      | `pricing-health-hourly` (`:42` each hour) | Price freshness, per-source coverage, FK soft-integrity, staging drain, PK collisions |
| `mtgstock.*` (existing) | `ops.integrity.mtgstock_report` | n/a (run by `pipeline-health-check`) | Per-run pipeline metrics — see [`MTGSTOCK_PIPELINE.md`](MTGSTOCK_PIPELINE.md) |
| **on-demand audit** | `ops.audit.scryfall_identifier_coverage` | n/a (run when investigating identifier-shape questions) | Streams a Scryfall raw bulk JSON file and compares against `card_external_identifier` row-for-row — see §Audit service below |

All three runners go through the shared `_metric_runner.run_metric_report` helper in `src/automana/core/services/ops/_metric_runner.py`.

---

## `card_catalog.*` metrics

Source: `src/automana/core/metrics/card_catalog/`. Backed by `CardReferenceRepository` (`src/automana/core/repositories/card_catalog/card_repository.py`).

| Path | Category | Severity | What it catches |
|---|---|---|---|
| `card_catalog.identifier_coverage.scryfall_id` | health | `≤99% → WARN`, `≤95% → ERROR` | The 113k-orphan incident — silent JOIN failures when `card_identifier_ref` is empty or a name is misspelled. Headline metric. |
| `card_catalog.identifier_coverage.oracle_id` | health | `≤99% → WARN`, `≤95% → ERROR` | Bulk identifier backfill stalled mid-run. **Measured against `unique_cards_ref`, not `card_version`** — `oracle_id` is per-abstract-card (one value shared across all printings of the same MTG card). Per-printing measurement would under-report by the average reprint rate (~3x). |
| `card_catalog.identifier_coverage.tcgplayer_id` | health | `≤80% → WARN`, `≤60% → ERROR` | TCGPlayer mapping pipeline failure. Lower threshold reflects that regional/promo cards may legitimately lack a TCGPlayer ID. |
| `card_catalog.identifier_coverage.cardmarket_id` | health | `≤70% → WARN`, `≤50% → ERROR` | Same as above, even lower threshold reflecting Cardmarket's narrower regional coverage. |
| `card_catalog.identifier_coverage.multiverse_id` | volume | none (informational) | Tracks the count of a deprecated identifier — no pass/fail, just drift detection. |
| `card_catalog.identifier_coverage.tcgplayer_etched_id` | volume | none (informational) | Etched-printing count; expected to be a tiny subset. |
| `card_catalog.print_coverage.orphan_unique_cards` | health | `≥5 → WARN`, `≥50 → ERROR` | `unique_cards_ref` rows with zero `card_version` children. Small counts are benign (tokens/emblems); large counts mean a set ingest stalled. |
| `card_catalog.duplicate_detection.external_id_value_collision` | health | `≥1 → ERROR` | Count of `(card_identifier_ref_id, value)` pairs shared by more than one `card_version_id` **for per-printing-unique identifiers only** (`scryfall_id`, `multiverse_id`, `tcgplayer_etched_id`, `mtgjson_id`). `oracle_id`, `tcgplayer_id`, and `cardmarket_id` are excluded — they legitimately share values across multiple card_version rows. Any non-zero count = ingest duplicate or upstream data error. |

`details` for coverage metrics carries `{identifier_name, covered, total}` so the operator can see the raw counts behind the percentage.

---

## `pricing.*` metrics

Source: `src/automana/core/metrics/pricing/`. Backed by `PriceRepository` (`src/automana/core/repositories/app_integration/mtg_stock/price_repository.py`) and `OpsRepository`.

| Path | Category | Severity | What it catches |
|---|---|---|---|
| `pricing.freshness.price_observation_max_age_days` | timing | `≥2 → WARN`, `≥7 → ERROR` | Days since the most recent `price_observation.ts_date`. Daily ingests should land same/next day. |
| `pricing.freshness.max_per_source_lag_hours` | timing | `≥48 → WARN`, `≥120 → ERROR` | Headline = MAX across sources; `details["per_source"]` carries the breakdown. Catches one source stalling while others run. |
| `pricing.coverage.min_per_source_observation_coverage_pct` | health | `≤50 → WARN`, `≤20 → ERROR` | MIN across sources of % `source_product` rows with an observation in the last 30 days. Per-source breakdown in `details["per_source"]`. |
| `pricing.referential.product_without_mtg_card_products` | health | `≥5 → WARN`, `≥20 → ERROR` | `pricing.product_ref` rows whose `game_id` matches the `mtg` row in `pricing.card_game` but have no `pricing.mtg_card_products` row. Orphans from partial promotion. |
| `pricing.referential.observation_without_source_product` | health | `≥1 → WARN`, `≥10 → ERROR` | `price_observation` rows whose `source_product_id` no longer exists. Hard FK should make this 0. |
| `pricing.staging.stg_price_observation_residual_count` | volume | `≥1M → WARN`, `≥5M → ERROR` | `stg_price_observation` should drain to ~0 between runs. Sustained large counts mean stage 3 failed to drain. |
| `pricing.duplicate_detection.observation_duplicates_on_pk` | health | `≥1 → ERROR` | Composite-PK violation in `price_observation`. Should always be 0. |

---

## CLI usage

Both runners are invoked via `automana-run`:

```bash
# Full report
automana-run ops.integrity.card_catalog_report
automana-run ops.integrity.pricing_report

# Filter by category — skip informational counts, keep only health checks
automana-run ops.integrity.card_catalog_report --category health

# Run a single metric
automana-run ops.integrity.card_catalog_report --metrics card_catalog.identifier_coverage.scryfall_id

# Comma-separated list of metrics
automana-run ops.integrity.pricing_report --metrics pricing.freshness.price_observation_max_age_days,pricing.coverage.min_per_source_observation_coverage_pct
```

Both runners accept `metrics`, `category`. `mtgstock_report` additionally accepts `ingestion_run_id`. Pipe to `jq` for further processing — note `automana-run` interleaves JSON log lines on stdout, so filter them out:

```bash
automana-run ops.integrity.card_catalog_report 2>/dev/null \
  | grep -v '^{"ts":' | grep -v '^Executing query' | jq '.errors'
```

### Real output

Run against the dev DB on 2026-04-25, the report immediately surfaced an oracle_id coverage gap that no other check was catching:

```
check_set:    card_catalog_report
total_checks: 8    errors: 1    warnings: 0    ok: 7

card_catalog.identifier_coverage.scryfall_id          ok    100.0   covered=113776 total=113776
card_catalog.identifier_coverage.oracle_id         ERROR     32.73  covered=37236 total=113776   ← real gap
card_catalog.identifier_coverage.tcgplayer_id         ok     84.92  covered=96618 total=113776
card_catalog.identifier_coverage.cardmarket_id        ok     81.79  covered=93060 total=113776
card_catalog.identifier_coverage.multiverse_id        ok     69535
card_catalog.identifier_coverage.tcgplayer_etched_id  ok      1220
card_catalog.print_coverage.orphan_unique_cards       ok        0
card_catalog.duplicate_detection.external_id_value_collision  ok  0
```

The standard envelope (`check_set`, `total_checks`, `error_count`, `warn_count`, `ok_count`, `errors`, `warnings`, `passed`, `rows`) is built by `_build_report` in `src/automana/core/services/ops/integrity_checks.py` and is identical across all `ops.integrity.*` services.

---

## Audit service: `ops.audit.scryfall_identifier_coverage`

When an identifier-coverage metric reads suspicious — too low, drifting, or you suspect the metric formulation itself — run the audit. It streams a Scryfall raw bulk JSON file (auto-discovers the newest under `/data/automana_data/scryfall/raw_files/` if no path is passed), tallies per-identifier source presence and distinct-value counts, queries the matching DB-side counts, and prints one row per identifier with the source-vs-DB gap.

```bash
# Auto-discover the newest raw file
automana-run ops.audit.scryfall_identifier_coverage

# Pin a specific file
automana-run ops.audit.scryfall_identifier_coverage --raw_file_path /data/automana_data/scryfall/raw_files/1_20260425_default-cards-20260424211240.json
```

Each row's `details` reports:

- `classification` — `per-printing` (1:1 ratio of refs to distinct values), `per-printing-with-collisions` (mild ~1.0x–1.5x), or `per-abstract-card` (≥1.5x — the value is shared across multiple printings; `tcgplayer_id`/`cardmarket_id` fall here intentionally).
- `source_pct` / `stored_pct` / `gap_pct` — what fraction of the universe has this identifier in the file vs in the DB. Severity is `OK` if `gap_pct < 1`, `WARN` ≥ 1, `ERROR` ≥ 5.
- The denominator on the DB side switches by classification: per-abstract-card identifiers measure against `unique_cards_ref`; per-printing identifiers measure against `card_version`. Same semantics as the corresponding `identifier_coverage.*` metric, so an audit row should match its metric's value within rounding.

This is the analysis that surfaced the original `oracle_id` metric-design bug — `oracle_id` showed `per-abstract-card` classification (3.05 refs/distinct, matching MTG's average reprint rate), revealing that the per-`card_version` measurement was structurally wrong rather than the ETL being broken.

Real output against the dev DB on 2026-04-25:

```
file_cards: 113776    db_card_versions: 113776    db_unique_cards: 36819
errors: 0    warnings: 2    ok: 4

IDENTIFIER             CLASS                   SEV   SRC%  STORED%   GAP  src_distinct  refs/dist
-------------------------------------------------------------------------------------------------
scryfall_id            per-printing             OK 100.00   100.00  0.00       113776       1.00
oracle_id              per-abstract-card        OK  99.93    99.84  0.09        37236       3.05
tcgplayer_id           per-printing           WARN  85.99    84.92  1.07        96618       1.01
cardmarket_id          per-printing           WARN  82.84    81.79  1.05        93060       1.01
multiverse_id          per-printing             OK  61.12    61.12  0.00        70133       1.00
tcgplayer_etched_id    per-printing             OK   1.08     1.07  0.01         1220       1.00
```

The two WARNs reflect ~1% of `tcgplayer_id` and `cardmarket_id` values that are shared across multiple printings (typically foil/non-foil pairs of the same physical product). This is the expected post-fix state — the `UNIQUE (card_identifier_ref_id, value)` constraint was intentionally dropped so both card_version rows can own their external_identifier row for the shared product ID. The WARN gap will resolve to ~0 once the Scryfall pipeline runs against the updated schema (the previously-dropped second printing row will now be inserted).

The audit is registered under the `ops.audit.*` namespace, **not** `ops.integrity.*`, so the `pipeline-health-check` skill does not auto-discover it. This is intentional — it's a heavy I/O operation (~5s for a 512MB raw file) meant for on-demand investigation.

---

## Beat schedule

From `src/automana/worker/celeryconfig.py`:

```python
"card-catalog-health-daily": {
    "task": "run_service",
    "schedule": crontab(hour=4, minute=15),  # 04:15 AEST — after the daily ingests
    "kwargs": {"path": "ops.integrity.card_catalog_report"},
},
"pricing-health-hourly": {
    "task": "run_service",
    "schedule": crontab(minute=42),  # off-the-hour to avoid the Celery cluster
    "kwargs": {"path": "ops.integrity.pricing_report"},
},
```

The `timezone` setting at the top of `celeryconfig.py` resolves to `Australia/Sydney`, so crontab values are interpreted in AEST. Card-catalog runs once a day because data shape is slow-changing; pricing runs hourly because freshness can degrade well within 24h.

Both entries call the generic `run_service` Celery task (registered in `src/automana/worker/main.py`) with the runner's service path — no per-runner wrapper task needed.

---

## Auto-discovery by the `pipeline-health-check` skill

The skill discovers any service registered as `ops.integrity.*` directly from `ServiceRegistry`. Registering a new runner is enough — the skill picks it up with no edits needed:

```python
import automana.core.metrics.card_catalog  # noqa: F401  — register card_catalog.* metrics
from automana.core.service_registry import ServiceRegistry

@ServiceRegistry.register("ops.integrity.card_catalog_report", db_repositories=["card", "ops"])
async def card_catalog_report(...): ...
```

The skill then runs every `ops.integrity.*` service, renders a Discord-friendly summary, and (with operator confirmation) posts it.

---

## Adding a metric to an existing family

The general flow is documented in [`METRICS_REGISTRY.md`](METRICS_REGISTRY.md#walkthrough--adding-a-metric). Family-specific notes:

- **`card_catalog.*`** — pick a module under `src/automana/core/metrics/card_catalog/` (`identifier_metrics.py` for identifier coverage, `catalog_metrics.py` for shape checks). Add the function to `__init__.py` if you create a new module. The `card_catalog_report` runner picks it up automatically via `MetricRegistry.select(prefix="card_catalog.")`.
- **`pricing.*`** — pick a module under `src/automana/core/metrics/pricing/` (`freshness_metrics.py`, `coverage_metrics.py`, `integrity_metrics.py`). Same auto-pickup via the `pricing.` prefix.
- **New family** — create the package, register at least one metric, create a runner service that delegates to `_metric_runner.run_metric_report` with the new prefix, and register the runner module in all three `SERVICE_MODULES` profiles in `src/automana/core/service_modules.py`.

---

## Out of scope (future work)

The full operational `db.*` family — vacuum, bloat, connections, TimescaleDB chunk health, indexes, locks, WAL, stats freshness, disk size — is deferred. It needs:

- A new `DbStatsRepository` querying `pg_catalog`, `pg_stat_*`, `timescaledb_information.*`.
- A `pg_monitor` role grant on the role that runs the report (current role-per-schema design doesn't grant this).
- A decision on `pgstattuple` extension availability for exact bloat measurement.

Tracked as Option C in `docs/superpowers/specs/2026-04-25-db-health-metrics-design.md` §9.

---

## Related docs

- [`METRICS_REGISTRY.md`](METRICS_REGISTRY.md) — registry decorator, severity types, runner dispatch internals
- [`MTGSTOCK_PIPELINE.md`](MTGSTOCK_PIPELINE.md) — the first metric family (per-run pipeline metrics)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — layer overview including `core/metrics/`
- [`OPERATIONS.md`](OPERATIONS.md) — pipeline-health-check skill, integrity reports
