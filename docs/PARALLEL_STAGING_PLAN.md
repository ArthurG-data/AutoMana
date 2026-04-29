# Plan: Parallel `load_staging_prices_batched`

## Context and cost/benefit

The current `from_raw_to_staging` pipeline step calls
`pricing.load_staging_prices_batched` on a single connection, which processes
~14 years of price history in 171 serial 30-day batches. At ~100% single-core
CPU the full historical backfill takes ~30 hours. **Daily production runs
process one batch and are already instant** — this change only pays off on full
DB rebuilds. Factor that into scheduling before committing.

Expected speedup with 4 workers: **3–4× on CPU**. WAL throughput becomes the
new ceiling above ~4 workers (see Phase 0).

---

## Phase 0 — Postgres config tuning (prerequisite, no code)

The current dev config is underpowered for parallel bulk writes. The logs
already show `checkpoints are occurring too frequently (29 seconds apart)` on a
*single* worker. Without these changes, adding workers will produce checkpoint
stalls rather than proportional speedup.

Edit `deploy/docker-compose.dev.yml` under the `postgres` service `command`:

| Parameter | Current | Recommended |
|---|---|---|
| `shared_buffers` | 128 MB | 6 GB (≈ 20% of 30 GB RAM) |
| `max_wal_size` | 1 GB | 12 GB |
| `checkpoint_timeout` | 5 min | 20 min |
| `max_worker_processes` | 8 | 16 |

`synchronous_commit` is already set to `off` per-batch inside the procedure —
no change needed there.

---

## Phase 1 — Migration: add date-range parameters to the procedure

**New file:** `src/automana/database/SQL/migrations/migration_17_parallel_staging_range.sql`

Modify `pricing.load_staging_prices_batched` to accept optional date bounds.
The change is fully **backward-compatible**: callers that omit the new params
get identical behaviour to today.

### Signature change

```sql
CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched(
    source_name        VARCHAR(20),
    batch_days         INT     DEFAULT 30,
    p_ingestion_run_id INT     DEFAULT NULL,
    p_start_date       DATE    DEFAULT NULL,   -- new: restrict to this window
    p_end_date         DATE    DEFAULT NULL    -- new: restrict to this window
)
```

### Body change — replace the unconditional min/max scan

```sql
-- Before:
SELECT min(ts_date), max(ts_date)
INTO v_min, v_max
FROM pricing.raw_mtg_stock_price;

-- After:
SELECT
    GREATEST(min(ts_date), COALESCE(p_start_date, min(ts_date))),
    LEAST(  max(ts_date),  COALESCE(p_end_date,   max(ts_date)))
INTO v_min, v_max
FROM pricing.raw_mtg_stock_price
WHERE (p_start_date IS NULL OR ts_date >= p_start_date)
  AND (p_end_date   IS NULL OR ts_date <= p_end_date);
```

No other changes to the procedure body are required.

---

## Phase 2 — Repository: chunk boundary fetch + ranged call

**File:** `src/automana/core/repositories/app_integration/mtg_stock/price_repository.py`

### 2a — `fetch_chunk_boundaries`

Worker date ranges must snap to Timescale chunk boundaries. If a boundary falls
inside a chunk, two workers compete to decompress that chunk and serialize on
its lock — eliminating the benefit of parallelism.

```python
async def fetch_chunk_boundaries(self) -> list:
    """Ordered list of chunk-start dates for pricing.price_observation.

    Used by the parallel coordinator to snap worker partitions to real
    chunk edges and avoid cross-worker decompression lock contention.
    """
    rows = await self.execute_query("""
        SELECT DISTINCT
            to_timestamp(range_start / 1e9)::date AS chunk_start
        FROM timescaledb_information.chunks
        WHERE hypertable_schema = 'pricing'
          AND hypertable_name   = 'price_observation'
        ORDER BY 1
    """)
    return [r["chunk_start"] for r in rows]
```

### 2b — `call_load_stage_from_raw_ranged`

```python
async def call_load_stage_from_raw_ranged(
    self,
    source_name: str,
    start_date,
    end_date,
    batch_days: int = 30,
) -> None:
    """Run load_staging_prices_batched over [start_date, end_date] only.

    Passes p_ingestion_run_id=NULL so the procedure writes no per-batch
    ops rows — the parallel coordinator writes a single summary row instead,
    avoiding batch_seq collisions between workers.
    """
    await self.connection.execute(
        "SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0"
    )
    try:
        await self.connection.execute(
            "CALL pricing.load_staging_prices_batched"
            "($1::varchar, $2::int, NULL, $3::date, $4::date);",
            source_name,
            batch_days,
            start_date,
            end_date,
        )
    finally:
        await self.connection.execute(
            "RESET timescaledb.max_tuples_decompressed_per_dml_transaction"
        )
```

---

## Phase 3 — Service: parallel coordinator

**File:** `src/automana/core/services/app_integration/mtg_stock/data_staging.py`

Add a new registered service alongside the existing `from_raw_to_staging`.
The existing service stays intact as a fallback.

### Partition helper (module-level, not registered)

```python
def _snap_partitions(raw_min, raw_max, chunk_boundaries, n_workers):
    """Divide [raw_min, raw_max] into n_workers non-overlapping date ranges,
    snapping boundaries to the nearest chunk edge to avoid lock contention.

    Returns a list of (start_date, end_date) tuples.
    """
    from datetime import timedelta

    # Filter boundaries that fall inside [raw_min, raw_max]
    edges = sorted(
        b for b in chunk_boundaries
        if raw_min <= b <= raw_max
    )
    # Always include endpoints
    all_edges = sorted({raw_min} | set(edges) | {raw_max + timedelta(days=1)})

    # Spread n_workers evenly across the edge list
    step = max(1, len(all_edges) // n_workers)
    split_points = all_edges[::step]

    partitions = []
    for i in range(len(split_points) - 1):
        start = split_points[i]
        end   = split_points[i + 1] - timedelta(days=1)
        if start <= end:
            partitions.append((start, end))

    # Merge any remainder into the last partition
    if partitions and partitions[-1][1] < raw_max:
        partitions[-1] = (partitions[-1][0], raw_max)

    return partitions
```

### Worker coroutine (module-level, not registered)

```python
async def _staging_worker(pool, source_name, start_date, end_date, batch_days, worker_id):
    """Acquire a dedicated connection and run load_staging_prices_batched
    over the assigned date window.

    Uses a raw pool connection rather than the injected repository connection
    so each worker has an independent session — required because
    SET timescaledb.max_tuples_decompressed_per_dml_transaction is session-scoped
    and the procedure issues internal COMMITs that would reset SET LOCAL.
    """
    async with pool.acquire() as conn:
        repo = PriceRepository(conn)
        logger.info(
            "staging_worker: starting",
            extra={"worker_id": worker_id, "start": str(start_date), "end": str(end_date)},
        )
        await repo.call_load_stage_from_raw_ranged(
            source_name=source_name,
            start_date=start_date,
            end_date=end_date,
            batch_days=batch_days,
        )
        logger.info(
            "staging_worker: done",
            extra={"worker_id": worker_id, "start": str(start_date), "end": str(end_date)},
        )
```

The `pool` reference must be threaded in from the coordinator. The ServiceManager
already holds the pool; expose it via a lightweight accessor or pass it explicitly.
This is the **only** place in the codebase where a service touches the pool directly
— document the exception and don't generalise it.

### Registered service

```python
@ServiceRegistry.register(
    path="mtg_stock.data_staging.from_raw_to_staging_parallel",
    db_repositories=["price", "ops"],
    runs_in_transaction=False,
    command_timeout=86400,
)
async def from_raw_to_staging_parallel(
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int = None,
    source_name: str = "mtgstocks",
    n_workers: int = 4,
    batch_days: int = 30,
):
    """Parallel variant of from_raw_to_staging.

    Divides the raw date range into n_workers non-overlapping windows snapped
    to price_observation chunk boundaries, then runs one DB session per window
    concurrently via asyncio.gather. Workers pass p_ingestion_run_id=NULL to
    avoid batch_seq collisions; this coordinator writes a single summary ops
    row on completion.
    """
    import asyncio
    from datetime import date as date_type

    async with track_step(ops_repository, ingestion_run_id, "raw_to_staging"):
        # 1. Discover date range
        rows = await price_repository.execute_query(
            "SELECT min(ts_date) AS d_min, max(ts_date) AS d_max"
            " FROM pricing.raw_mtg_stock_price"
        )
        if not rows or rows[0]["d_min"] is None:
            logger.info("from_raw_to_staging_parallel: raw table is empty, nothing to do")
            return {}

        raw_min: date_type = rows[0]["d_min"]
        raw_max: date_type = rows[0]["d_max"]

        # 2. Snap partitions to chunk boundaries
        chunk_bounds = await price_repository.fetch_chunk_boundaries()
        partitions = _snap_partitions(raw_min, raw_max, chunk_bounds, n_workers)

        logger.info(
            "from_raw_to_staging_parallel: launching workers",
            extra={"n_workers": len(partitions), "raw_min": str(raw_min), "raw_max": str(raw_max)},
        )

        # 3. Run workers concurrently — each acquires its own pool connection
        pool = price_repository.connection._pool  # implementation detail; wrap if pool accessor added
        await asyncio.gather(*[
            _staging_worker(pool, source_name, start, end, batch_days, i)
            for i, (start, end) in enumerate(partitions)
        ])
```

> **Note on pool access:** `price_repository.connection._pool` reaches into asyncpg
> internals. The cleaner approach is to add a `pool` property to `AbstractRepository`
> (or `ServiceManager`) and expose it explicitly. Do that in the same PR.

---

## Phase 4 — Pipeline wiring

**File:** `src/automana/worker/tasks/pipelines.py`

Swap one line in `mtgStock_download_pipeline`. Keep the serial version registered.

```python
# Before:
run_service.s("mtg_stock.data_staging.from_raw_to_staging",
              source_name="mtgstocks"),

# After:
run_service.s("mtg_stock.data_staging.from_raw_to_staging_parallel",
              source_name="mtgstocks",
              n_workers=4),
```

`n_workers=4` is a conservative start. Tune upward after validation (Phase 5).

---

## Phase 5 — Validation before adopting in production

Run this against a clean dev DB before merging:

1. Load a narrow raw slice into `raw_mtg_stock_price`: `2018-01-01 → 2018-12-31`
2. Run the **serial** version:
   ```bash
   automana-run mtg_stock.data_staging.from_raw_to_staging --source_name mtgstocks
   ```
3. Capture a fingerprint:
   ```sql
   SELECT COUNT(*),
          MD5(string_agg(ts_date::text || source_product_id::text || sold_avg_cents::text,
                         ',' ORDER BY ts_date, source_product_id))
   FROM pricing.price_observation;
   ```
4. Truncate `price_observation`, reload the same raw slice.
5. Run the **parallel** version:
   ```bash
   automana-run mtg_stock.data_staging.from_raw_to_staging_parallel \
     --source_name mtgstocks --n_workers 4
   ```
6. Capture the same fingerprint. **Must match exactly.**

---

## Delivery order

| # | Phase | Files touched | Blocking? |
|---|-------|---------------|-----------|
| 0 | Postgres tuning | `docker-compose.dev.yml` | Yes — do before any parallel run |
| 1 | Migration | `migrations/migration_17_*.sql`, `schemas/06_prices.sql` | Yes — procedure must exist before repo methods |
| 2 | Repository additions | `price_repository.py` | Yes |
| 3 | Coordinator service | `data_staging.py` | Yes |
| 4 | Pipeline swap | `pipelines.py` | After validation |
| 5 | Validation | Manual | Gate for Phase 4 |

Phases 1–3 can be written and unit-tested without a running DB. Phase 4 is a
one-line change gated on Phase 5 passing.
