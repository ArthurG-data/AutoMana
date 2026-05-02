# MTGStock Link Rate Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 0% MTGStock card link rate by correcting a case-sensitivity bug in the staging procedure's set+collector fallback, backfilling missing mtgstock_id mappings, and documenting the irreducible rejects for future investigation.

**Architecture:** Two SQL procedures (`load_staging_prices_batched`, `resolve_price_rejects`) have a broken step-3 fallback because `set_code = set_abbr` is a case-sensitive equality while the catalog stores lowercase (`'evg'`) and the raw table stores uppercase (`'EVG'`). Fix is `LOWER(set_abbr)` in both procedures. A separate Python backfill script pre-populates `card_external_identifier` with `mtgstock_id` entries derived from cross-referencing external IDs already in the raw table, increasing the faster step-1 hit rate. Investigation markdown files document irreducible rejects (no identifiers, unknown set codes) for manual triage.

**Tech Stack:** PostgreSQL 17 + TimescaleDB, asyncpg, Python 3.12, AutoMana `automana-run` CLI / `bootstrap`/`teardown` helpers.

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `src/automana/database/SQL/schemas/06_prices.sql` | Modify lines 719, 1393 | Source-of-truth schema — keep in sync with migration |
| `src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql` | Create | Idempotent `CREATE OR REPLACE` migration applied to live DB |
| `scripts/mtgstock_backfill_identifiers.py` | Create | One-time/re-runnable script to insert missing `mtgstock_id` → `card_version_id` entries via external IDs |
| `docs/investigate/mtgstock_no_identifier_prints.md` | Create | Documents the 10 raw print_ids that carry zero usable identifiers |
| `docs/investigate/mtgstock_missing_set_codes.md` | Create | Documents the 20 set codes in raw data that have no matching row in `card_catalog.sets` |

---

## Background: the three resolution paths

`pricing.load_staging_prices_batched` resolves MTGStock `print_id → card_version_id` in priority order:

1. **PRINT_ID** — `card_external_identifier WHERE identifier_name = 'mtgstock_id' AND value = print_id::text`
2. **EXTERNAL_ID** — scryfall_id → tcgplayer_id → cardtrader_id, joined against `card_external_identifier`
3. **SET_COLLECTOR** — `card_catalog.sets sr ON sr.set_code = u.set_abbr` → `card_version cv ON cv.collector_number = u.collector_number`

Step 3 is broken: PostgreSQL text equality is case-sensitive, catalog stores `'evg'`, raw stores `'EVG'`. This kills all 56,817 prints in step 3. Fix: `LOWER(u.set_abbr)` / `LOWER(r.set_abbr)`.

The same bug is present in `pricing.resolve_price_rejects` at line 1393.

**Expected link rate after fixes:**
- Current: ~24% (step 1 only, 13,571 / 56,817 prints matched)
- After LOWER fix: ~84–88% (step 3 newly resolves ~34k prints with collector numbers)
- Irreducible rejects: ~10 prints with zero identifiers + prints in 20 unknown set codes

---

## Task 1: Fix `06_prices.sql` (source of truth)

**Files:**
- Modify: `src/automana/database/SQL/schemas/06_prices.sql:719`
- Modify: `src/automana/database/SQL/schemas/06_prices.sql:1393`

- [ ] **Step 1: Apply the LOWER() fix to `load_staging_prices_batched` (line 719)**

In `src/automana/database/SQL/schemas/06_prices.sql`, line 719, change:
```sql
-- Before:
    ON sr.set_code = u.set_abbr
-- After:
    ON sr.set_code = LOWER(u.set_abbr)
```

The surrounding context (lines 710–727) must look like this after the edit:
```sql
  -- (3) fallback by set + collector (+ optional name match)
  DROP TABLE IF EXISTS tmp_map_fallback;
  CREATE TEMP TABLE tmp_map_fallback ON COMMIT DROP AS
  SELECT DISTINCT
    u.set_abbr,
    u.collector_number,
    cv.card_version_id
  FROM tmp_raw_batch u
  JOIN card_catalog.sets sr
    ON sr.set_code = LOWER(u.set_abbr)
  JOIN card_catalog.card_version cv
    ON cv.set_id = sr.set_id
  AND cv.collector_number::text = u.collector_number
  LEFT JOIN card_catalog.unique_cards_ref uc
    ON uc.unique_card_id = cv.unique_card_id
  WHERE u.set_abbr IS NOT NULL
    AND u.collector_number IS NOT NULL
    AND (u.card_name IS NULL OR uc.card_name IS NULL OR lower(uc.card_name) = lower(u.card_name));
```

- [ ] **Step 2: Apply the LOWER() fix to `resolve_price_rejects` (line 1393)**

In `src/automana/database/SQL/schemas/06_prices.sql`, line 1393, change:
```sql
-- Before:
      ON s.set_code = r.set_abbr
-- After:
      ON s.set_code = LOWER(r.set_abbr)
```

The surrounding context (lines 1389–1402) must look like this after the edit:
```sql
  map_fb AS (
    SELECT DISTINCT r.set_abbr, r.collector_number, cv.card_version_id
    FROM tmp_rejects r
    JOIN card_catalog.sets s
      ON s.set_code = LOWER(r.set_abbr)
    JOIN card_catalog.card_version cv
      ON cv.set_id = s.set_id
     AND cv.collector_number::text = r.collector_number
    LEFT JOIN card_catalog.unique_cards_ref uc
      ON uc.unique_card_id = cv.unique_card_id
    WHERE r.set_abbr IS NOT NULL
      AND r.collector_number IS NOT NULL
      AND (r.card_name IS NULL OR uc.card_name IS NULL OR lower(uc.card_name) = lower(r.card_name))
  )
```

- [ ] **Step 3: Verify the grep for the old text returns nothing**

```bash
grep -n "ON sr.set_code = u.set_abbr\|ON s.set_code = r.set_abbr" \
  src/automana/database/SQL/schemas/06_prices.sql
```

Expected: no output (zero matches).

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/schemas/06_prices.sql
git commit -m "fix(pricing): LOWER(set_abbr) in staging+reject set-collector fallback

Step-3 join in load_staging_prices_batched and resolve_price_rejects
used case-sensitive equality (set_code = set_abbr).  The catalog stores
set codes in lowercase; the raw MTGStock table stores them in uppercase.
The mismatch silently zeroed step-3 resolution for all 56k prints.

Fixes mtgstock.link_rate_pct = 0% (run 3).  Expected link rate after
full staging re-run: ~84-88% (from ~24% today)."
```

---

## Task 2: Create migration 16

The migration directory doesn't exist yet. This task creates it and the migration file, then applies it to the dev DB so the live procedure matches `06_prices.sql`.

**Files:**
- Create: `src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql`

- [ ] **Step 1: Create the migrations directory**

```bash
mkdir -p src/automana/database/SQL/migrations
```

- [ ] **Step 2: Create migration file**

Create `src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql` with this content:

```sql
-- Migration 16: Fix case-sensitive set_code comparison in staging procedures
--
-- Both pricing.load_staging_prices_batched and pricing.resolve_price_rejects
-- contained:
--     JOIN card_catalog.sets sr ON sr.set_code = u.set_abbr
-- PostgreSQL text equality is case-sensitive.  The catalog stores set codes
-- in lowercase ('evg'); raw_mtg_stock_price stores them in uppercase ('EVG').
-- The mismatch silently broke step-3 (SET_COLLECTOR) resolution for all
-- 56,817 print_ids, collapsing the link rate to ~24% (step 1 only).
--
-- Fix: LOWER(set_abbr) in both procedures.
-- Idempotent: CREATE OR REPLACE is safe to re-run.

-- ─────────────────────────────────────────────────────────────────────────────
-- Re-create load_staging_prices_batched with the LOWER() fix.
-- Full body copied from src/automana/database/SQL/schemas/06_prices.sql.
-- Only changed line: ON sr.set_code = LOWER(u.set_abbr)   (was = u.set_abbr)
-- ─────────────────────────────────────────────────────────────────────────────
```

Then append the full body of `load_staging_prices_batched` from `06_prices.sql` (lines 486–1284) with the LOWER fix already applied, followed by the full body of `resolve_price_rejects` (lines 1287–1599) with the LOWER fix applied.

> **Implementation note for the agent executing this plan:** Rather than duplicating ~800 lines in this document, use the following approach to build the migration file:
> ```bash
> # Extract load_staging_prices_batched (lines 486-1284)
> sed -n '486,1284p' src/automana/database/SQL/schemas/06_prices.sql \
>   >> src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql
>
> echo "" >> src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql
>
> # Extract resolve_price_rejects (lines 1287-1599)
> sed -n '1287,1599p' src/automana/database/SQL/schemas/06_prices.sql \
>   >> src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql
> ```
> The file header (the comment block above) must be prepended manually. Then verify the grep below confirms LOWER() is present and the old form is absent.

- [ ] **Step 3: Verify the migration file contains the fix and not the old form**

```bash
grep -n "LOWER(u.set_abbr)\|LOWER(r.set_abbr)" \
  src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql
# Expected: 2 matches — one per procedure

grep -n "= u.set_abbr\|= r.set_abbr" \
  src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql
# Expected: no output
```

- [ ] **Step 4: Apply the migration to the dev DB**

```bash
cd /home/arthur/projects/AutoMana

# Get the connection string from settings
PGPASSWORD=$(./.venv/bin/python -c \
  "from automana.core.settings import get_settings; s=get_settings(); print(s.APP_ADMIN_PASSWORD)" \
  2>/dev/null)

psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql
```

Expected output: two `CREATE PROCEDURE` / `CREATE FUNCTION` lines with no errors.

- [ ] **Step 5: Smoke-test the fix via a quick query**

```bash
./.venv/bin/python - << 'EOF' 2>/dev/null
import asyncio
from automana.tools.tui.shared import bootstrap, teardown

async def main():
    pool = await bootstrap()
    try:
        async with pool.acquire() as conn:
            # Counts that should be > 0 after the fix
            rows = await conn.fetch("""
                SELECT COUNT(DISTINCT r.print_id) AS would_resolve_via_step3
                FROM pricing.raw_mtg_stock_price r
                JOIN card_catalog.sets s ON s.set_code = LOWER(r.set_abbr)
                JOIN card_catalog.card_version cv
                  ON cv.set_id = s.set_id
                 AND cv.collector_number::text = r.collector_number
                WHERE r.collector_number IS NOT NULL
            """)
            print("Prints resolvable via fixed step 3:", rows[0]["would_resolve_via_step3"])
    finally:
        await teardown(pool)

asyncio.run(main())
EOF
```

Expected: a number substantially greater than 0 (postgres expert estimated ~34k additional prints).

- [ ] **Step 6: Commit**

```bash
git add src/automana/database/SQL/migrations/16_fix_staging_lower_set_code.sql
git commit -m "chore(db): add migration 16 — LOWER(set_abbr) in staging procedures

Applies the fix from 06_prices.sql to the live dev DB.  CREATE OR REPLACE
is idempotent; safe to re-run."
```

---

## Task 3: Create mtgstock_id backfill script

Prints already resolved via step 2 (EXTERNAL_ID) during staging get their `mtgstock_id` inserted into `card_external_identifier` inline (step 3e in the procedure). But the 13,571 that are currently in `card_external_identifier` were populated by earlier runs. For print_ids that **have** external identifiers in the raw table but **no** `mtgstock_id` entry yet, this script pre-populates the mapping so future staging runs use the faster step-1 path.

**Files:**
- Create: `scripts/mtgstock_backfill_identifiers.py`

- [ ] **Step 1: Create the script**

Create `scripts/mtgstock_backfill_identifiers.py`:

```python
"""
mtgstock_backfill_identifiers.py

Pre-populates card_catalog.card_external_identifier with mtgstock_id entries
for every print_id in pricing.raw_mtg_stock_price that can be resolved to a
card_version_id via scryfall_id, tcgplayer_id, or cardtrader_id — but does
not yet have an existing mtgstock_id mapping.

The staging procedure (load_staging_prices_batched step 3e) does the same
thing inline during each run, but only for the prints it processes in that
batch window.  This script covers the full raw table in one pass so future
staging runs hit step 1 (O(1) hash lookup) instead of step 2 for every
already-resolved print.

Usage:
    cd /home/arthur/projects/AutoMana
    ./.venv/bin/python scripts/mtgstock_backfill_identifiers.py [--dry-run]

Options:
    --dry-run   Report how many rows would be inserted without modifying the DB.
"""
import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


DRY_RUN = "--dry-run" in sys.argv


async def main() -> None:
    # Import here so the script can only be run from the project root.
    from automana.tools.tui.shared import bootstrap, teardown

    pool = await bootstrap()
    try:
        async with pool.acquire() as conn:
            # 1. Resolve each distinct print_id to a card_version_id via
            #    external identifiers (scryfall > tcgplayer > cardtrader).
            #    Exclude print_ids already in card_external_identifier as
            #    mtgstock_id to keep the insert idempotent.
            rows = await conn.fetch("""
                WITH raw_ids AS (
                    SELECT DISTINCT
                        print_id,
                        scryfall_id,
                        tcg_id,
                        cardtrader_id
                    FROM pricing.raw_mtg_stock_price
                    WHERE print_id IS NOT NULL
                ),
                already_mapped AS (
                    SELECT cei.value::bigint AS print_id
                    FROM card_catalog.card_external_identifier cei
                    JOIN card_catalog.card_identifier_ref cir
                      ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
                     AND cir.identifier_name = 'mtgstock_id'
                ),
                candidates AS (
                    SELECT
                        r.print_id,
                        'scryfall_id'::text   AS identifier_name,
                        COALESCE(m.new_scryfall_id::text, r.scryfall_id) AS identifier_value,
                        1 AS prio
                    FROM raw_ids r
                    LEFT JOIN card_catalog.scryfall_migration m
                      ON NULLIF(r.scryfall_id, 'None')::uuid = m.old_scryfall_id
                     AND m.migration_strategy IN ('merge', 'move')
                     AND m.new_scryfall_id IS NOT NULL
                    WHERE r.scryfall_id IS NOT NULL
                      AND r.scryfall_id NOT IN ('', 'None')
                      AND r.print_id NOT IN (SELECT print_id FROM already_mapped)

                    UNION ALL
                    SELECT r.print_id, 'tcgplayer_id', r.tcg_id, 2
                    FROM raw_ids r
                    WHERE r.tcg_id IS NOT NULL
                      AND r.print_id NOT IN (SELECT print_id FROM already_mapped)

                    UNION ALL
                    SELECT r.print_id, 'cardtrader_id', r.cardtrader_id, 3
                    FROM raw_ids r
                    WHERE r.cardtrader_id IS NOT NULL
                      AND r.print_id NOT IN (SELECT print_id FROM already_mapped)
                ),
                joined AS (
                    SELECT c.print_id, c.prio, cei.card_version_id
                    FROM candidates c
                    JOIN card_catalog.card_identifier_ref cir
                      ON cir.identifier_name = c.identifier_name
                    JOIN card_catalog.card_external_identifier cei
                      ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
                     AND cei.value = c.identifier_value
                ),
                ranked AS (
                    SELECT *, row_number() OVER (PARTITION BY print_id ORDER BY prio) rn
                    FROM joined
                ),
                resolved AS (
                    SELECT print_id, card_version_id
                    FROM ranked
                    WHERE rn = 1
                ),
                -- avoid ambiguous mappings (one print_id → multiple card_version_id)
                unambiguous AS (
                    SELECT print_id, card_version_id
                    FROM resolved
                    WHERE print_id IN (
                        SELECT print_id FROM resolved
                        GROUP BY print_id HAVING COUNT(DISTINCT card_version_id) = 1
                    )
                ),
                -- avoid conflicts the other way (multiple print_ids → same card_version_id)
                pick_one_per_cv AS (
                    SELECT DISTINCT ON (card_version_id)
                        card_version_id,
                        print_id
                    FROM unambiguous
                    ORDER BY card_version_id, print_id
                )
                SELECT p.print_id, p.card_version_id
                FROM pick_one_per_cv p
            """)

            logger.info("Resolved %d print_id → card_version_id pairs via external IDs", len(rows))

            if DRY_RUN:
                logger.info("[dry-run] Would insert %d rows into card_external_identifier", len(rows))
                for r in rows[:20]:
                    logger.info("  print_id=%-8s → card_version_id=%s", r["print_id"], r["card_version_id"])
                if len(rows) > 20:
                    logger.info("  ... and %d more", len(rows) - 20)
                return

            if not rows:
                logger.info("Nothing to backfill — all resolvable print_ids already have mtgstock_id entries.")
                return

            # 2. Fetch the mtgstock_id ref_id once.
            ref_row = await conn.fetchrow(
                "SELECT card_identifier_ref_id FROM card_catalog.card_identifier_ref "
                "WHERE identifier_name = 'mtgstock_id' LIMIT 1"
            )
            if ref_row is None:
                raise RuntimeError("No card_identifier_ref row for 'mtgstock_id' — is the catalog seeded?")
            ref_id = ref_row["card_identifier_ref_id"]

            # 3. Bulk-insert, ignoring already-existing PK conflicts.
            inserted = await conn.executemany(
                """
                INSERT INTO card_catalog.card_external_identifier
                    (card_identifier_ref_id, card_version_id, value)
                VALUES ($1, $2, $3)
                ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING
                """,
                [(ref_id, r["card_version_id"], str(r["print_id"])) for r in rows],
            )
            logger.info(
                "Backfill complete: attempted %d inserts (conflicts silently skipped). "
                "Re-run to verify idempotency.",
                len(rows),
            )

    finally:
        await teardown(pool)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run in dry-run mode to verify the query works**

```bash
cd /home/arthur/projects/AutoMana
./.venv/bin/python scripts/mtgstock_backfill_identifiers.py --dry-run 2>&1 | grep -v "^{"
```

Expected output: `INFO Resolved N print_id → card_version_id pairs via external IDs` followed by sample rows. N should be > 0 (likely in the thousands).

- [ ] **Step 3: Run for real**

```bash
cd /home/arthur/projects/AutoMana
./.venv/bin/python scripts/mtgstock_backfill_identifiers.py 2>&1 | grep -v "^{"
```

Expected: `INFO Backfill complete: attempted N inserts`

- [ ] **Step 4: Verify the mtgstock_id count increased**

```bash
./.venv/bin/python - << 'EOF' 2>/dev/null
import asyncio
from automana.tools.tui.shared import bootstrap, teardown

async def main():
    pool = await bootstrap()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT COUNT(*) AS n
                FROM card_catalog.card_external_identifier cei
                JOIN card_catalog.card_identifier_ref cir
                  ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
                WHERE cir.identifier_name = 'mtgstock_id'
            """)
            print("mtgstock_id entries:", row["n"])
    finally:
        await teardown(pool)

asyncio.run(main())
EOF
```

Expected: a number greater than 13,571 (the pre-backfill count).

- [ ] **Step 5: Commit**

```bash
git add scripts/mtgstock_backfill_identifiers.py
git commit -m "feat(scripts): mtgstock_backfill_identifiers — pre-populate mtgstock_id entries

For print_ids in raw_mtg_stock_price that have scryfall_id, tcgplayer_id,
or cardtrader_id but no mtgstock_id entry in card_external_identifier, this
script resolves card_version_id via those external IDs and inserts the
mtgstock_id mapping so future staging runs hit the faster step-1 path.

Idempotent: ON CONFLICT DO NOTHING.  Run with --dry-run to preview."
```

---

## Task 4: Document unresolvable prints (no identifiers)

10 print_ids in `pricing.raw_mtg_stock_price` carry zero usable identifiers: `scryfall_id = NULL`, `tcg_id = NULL`, `cardtrader_id = NULL`, `collector_number = NULL`. These cannot be resolved by any of the three resolution paths and will always land in the reject table.

**Files:**
- Create: `docs/investigate/mtgstock_no_identifier_prints.md`

- [ ] **Step 1: Query the exact 10 prints to include in the document**

```bash
./.venv/bin/python - << 'EOF' 2>/dev/null
import asyncio
from automana.tools.tui.shared import bootstrap, teardown

async def main():
    pool = await bootstrap()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT print_id, card_name, set_abbr, scryfall_id,
                                tcg_id, cardtrader_id, collector_number
                FROM pricing.raw_mtg_stock_price
                WHERE scryfall_id IS NULL
                  AND tcg_id IS NULL
                  AND cardtrader_id IS NULL
                  AND collector_number IS NULL
                ORDER BY print_id
            """)
            for r in rows:
                print(dict(r))
    finally:
        await teardown(pool)

asyncio.run(main())
EOF
```

- [ ] **Step 2: Create the investigation document**

Create `docs/investigate/mtgstock_no_identifier_prints.md` with the following structure (fill in the actual 10 rows from Step 1):

```markdown
# MTGStock — Prints with No Resolvable Identifiers

**Date discovered:** 2026-04-26  
**Pipeline run:** mtg_stock_all run 3  
**Status:** Under investigation — these rows will always land in `pricing.stg_price_observation_reject`

## What We Found

After fixing the case-sensitivity bug in `load_staging_prices_batched` (migration 16),
the staging pipeline is expected to resolve ~84–88% of the 56,817 print_ids in
`pricing.raw_mtg_stock_price`.  The remaining ~10 prints listed here have **no
usable identifiers** in the MTGStocks export:

- `scryfall_id` is NULL
- `tcg_id` is NULL
- `cardtrader_id` is NULL
- `collector_number` is NULL

With no identifiers, all three resolution paths fail:
1. **PRINT_ID path** — `mtgstock_id` has never been mapped for these prints
2. **EXTERNAL_ID path** — no scryfall_id, tcgplayer_id, or cardtrader_id to cross-reference
3. **SET_COLLECTOR path** — requires a non-null `collector_number`

## The 10 Prints

| print_id | card_name | set_abbr | Notes |
|----------|-----------|----------|-------|
| (fill from query output) | | | |

## Why They Lack Identifiers

MTGStocks tracks certain token cards and very old promotional printings that
predate widespread use of collector numbers. The MTGStocks data export simply
omits external IDs for these entries. Known categories:

- **Tokens** (e.g. `Elemental`, `Goblin`, `Saproling`): Token cards were not
  consistently tracked in Scryfall's early data.  Their MTGStocks `info.json`
  files have `scryfallId: null` and `collector_number: null`.
- **Starter 2000 / S00 cards** (e.g. `Disenchant`, `Coercion`, `Goblin Hero`,
  `Wind Drake`): S00 is a small regional set with incomplete identifier coverage
  in the MTGStocks export.
- **Duel Decks Anthology legacy code `DD3`** (`Goblin Token`, `Saproling`):
  MTGStocks uses `DD3` for the all-in-one anthology reprint; Scryfall splits
  this into sub-set codes (`evg`, `dvd`, `jvc`, `gvl`).  The set code mismatch
  compounds the missing identifier problem.

## Resolution Options

### Option A — Manual mtgstock_id backfill (recommended for tokens)
1. Look up each print_id on the MTGStocks website (e.g. `https://www.mtgstocks.com/prints/<print_id>`).
2. Find the matching card in `card_catalog.card_version` (via name + set code).
3. Insert a row into `card_catalog.card_external_identifier`:
   ```sql
   INSERT INTO card_catalog.card_external_identifier
     (card_identifier_ref_id, card_version_id, value)
   SELECT cir.card_identifier_ref_id, '<card_version_id>', '<print_id>'
   FROM card_catalog.card_identifier_ref cir
   WHERE cir.identifier_name = 'mtgstock_id'
   ON CONFLICT DO NOTHING;
   ```
4. After inserting, mark the reject rows as resolvable by setting
   `is_terminal = FALSE` and clearing `terminal_reason` so `retry_rejects`
   picks them up.

### Option B — Mark as terminal (acceptable for cards not in catalog)
If a card genuinely doesn't exist in `card_catalog.card_version` (e.g. tokens
that Scryfall doesn't track), mark it terminal:
```sql
UPDATE pricing.stg_price_observation_reject
SET is_terminal = TRUE,
    terminal_reason = 'Token/legacy print: no identifier in MTGStocks export and no catalog entry'
WHERE print_id IN (<list of print_ids>);
```

### Option C — Add name+set fallback (not recommended)
Adding a 4th resolution path using `set_abbr + card_name` without
`collector_number` introduces ambiguity (many tokens share the same name
across sets).  The "Goblin Token" vs "Goblin" naming divergence across data
sources compounds this.  Only consider this if the number of affected prints
grows significantly.

## Next Steps

- [ ] Verify each print_id on mtgstocks.com and identify the canonical card
- [ ] For prints that exist in `card_catalog.card_version`, apply Option A
- [ ] For prints with no catalog entry, apply Option B
- [ ] After resolution, re-run `mtg_stock.data_staging.retry_rejects` to promote resolved rows
```

- [ ] **Step 3: Commit**

```bash
git add docs/investigate/mtgstock_no_identifier_prints.md
git commit -m "docs(investigate): document MTGStock prints with zero resolvable identifiers

10 print_ids in raw_mtg_stock_price carry no scryfall_id, tcg_id,
cardtrader_id, or collector_number. They will always reject under the
current 3-path resolution logic. Documents known causes (tokens, S00,
DD3 legacy code) and resolution options."
```

---

## Task 5: Document missing set codes (step 3 gaps)

20 `set_abbr` values in `pricing.raw_mtg_stock_price` have no matching row in `card_catalog.sets` even after `LOWER()` normalization. Prints in these sets fail step 3 even after migration 16.

**Files:**
- Create: `docs/investigate/mtgstock_missing_set_codes.md`

- [ ] **Step 1: Query each missing set code's print_id count**

```bash
./.venv/bin/python - << 'EOF' 2>/dev/null
import asyncio
from automana.tools.tui.shared import bootstrap, teardown

async def main():
    pool = await bootstrap()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    r.set_abbr,
                    COUNT(DISTINCT r.print_id) AS distinct_prints,
                    COUNT(DISTINCT r.print_id) FILTER (
                        WHERE r.scryfall_id IS NOT NULL AND r.scryfall_id NOT IN ('', 'None')
                    ) AS with_scryfall,
                    COUNT(DISTINCT r.print_id) FILTER (
                        WHERE r.tcg_id IS NOT NULL
                    ) AS with_tcg,
                    COUNT(DISTINCT r.print_id) FILTER (
                        WHERE r.collector_number IS NOT NULL
                    ) AS with_collector
                FROM pricing.raw_mtg_stock_price r
                WHERE NOT EXISTS (
                    SELECT 1 FROM card_catalog.sets s
                    WHERE s.set_code = LOWER(r.set_abbr)
                )
                  AND r.set_abbr IS NOT NULL
                GROUP BY r.set_abbr
                ORDER BY distinct_prints DESC
            """)
            for r in rows:
                print(dict(r))
    finally:
        await teardown(pool)

asyncio.run(main())
EOF
```

- [ ] **Step 2: Create the investigation document**

Create `docs/investigate/mtgstock_missing_set_codes.md`:

```markdown
# MTGStock — Set Codes Missing from card_catalog.sets

**Date discovered:** 2026-04-26  
**Pipeline run:** mtg_stock_all run 3  
**Status:** Under investigation

## What We Found

After migration 16 (LOWER fix), `load_staging_prices_batched` step 3
(SET_COLLECTOR fallback) joins `card_catalog.sets` using `LOWER(set_abbr)`.
The 20 set codes below still fail this join because they do not exist in the
catalog at all.  Prints in these sets can only resolve via step 1 (mtgstock_id)
or step 2 (external IDs).

## Missing Set Codes

| set_abbr | Distinct prints | Has scryfall | Has tcg | Has collector | Likely identity |
|----------|----------------|-------------|---------|---------------|----------------|
| DD3      | (from query)   | (from query)| (from query) | (from query) | MTGStocks legacy code for Duel Decks Anthology (Scryfall splits into: evg, dvd, jvc, gvl) |
| 30A-P    | | | | | 30th Anniversary Edition promos — Scryfall code may be `30a` |
| AAINR    | | | | | Arena event (AINR?) — no Scryfall equivalent |
| AATDM    | | | | | Arena event (ATDM?) |
| DA1      | | | | | Unknown legacy code |
| PAPAC    | | | | | Unknown promo code |
| PEURO    | | | | | European Championships promo (Scryfall: `euro`) |
| PPBLB    | | | | | Pre-release promo for Bloomburrow (Scryfall: `pblb`) |
| PPDFT    | | | | | Pre-release promo for Duskmourn (Scryfall: `pdft`) |
| PPDMU    | | | | | Pre-release promo for Dominaria United (Scryfall: `pdmu`) |
| PPDSK    | | | | | Pre-release promo for Kaldheim (Scryfall: `pkdm` or `pdsk`?) |
| PPEOE    | | | | | Pre-release promo for Edge of Eternities? |
| PPMKM    | | | | | Pre-release promo for Murders at Karlov Manor (Scryfall: `pmkm`) |
| PPOTJ    | | | | | Pre-release promo for Outlaws of Thunder Junction (Scryfall: `potj`) |
| PPTDM    | | | | | Pre-release promo |
| PPWOE    | | | | | Pre-release promo for Wilds of Eldraine (Scryfall: `pwoe`) |
| RMB1     | | | | | Unknown — possibly a regional/promo code |
| SLDC     | | | | | Unknown |
| SSK      | | | | | Unknown |
| (NULL)   | | | | | Print_ids with no set_abbr in MTGStocks export |

*(Fill in the print counts and identifier availability from Step 1 output.)*

## Root Causes

### 1. MTGStocks uses a legacy `DD3` code for Duel Decks Anthology
MTGStocks lumps all four Duel Decks Anthology sub-sets under `DD3`.
Scryfall models them separately (`evg`, `dvd`, `jvc`, `gvl`).

**Fix path:** Add a set code alias mapping, or resolve these prints via
their `scryfall_id` / `tcg_id` identifiers (most `DD3` prints do carry
external IDs, so step 2 should already handle them).

### 2. `PP*` codes are MTGStocks pre-release promo set codes
MTGStocks invented a `PP<set_code>` convention for pre-release promos.
Scryfall uses a `p<set_code>` convention for the same cards.

**Fix path (option A):** Add the `PP*` → `p*` mapping to the staging
procedure so that `LOWER('PPBLB')` → `'pblb'` lookup works:
```sql
-- In tmp_map_fallback step:
JOIN card_catalog.sets sr
  ON sr.set_code = CASE
    WHEN LOWER(u.set_abbr) LIKE 'pp%' THEN 'p' || LOWER(SUBSTRING(u.set_abbr FROM 3))
    ELSE LOWER(u.set_abbr)
  END
```
This would be migration 17.

**Fix path (option B):** Accept that pre-release promos resolve via
step 2 (scryfall_id / tcg_id), which is already correct for most of
these prints.  Treat `PP*` as structurally unresolvable in step 3 and
rely on step 1+2.

### 3. Unknown codes (`DA1`, `RMB1`, `SLDC`, `SSK`, `PAPAC`, `PEURO`)
These appear to be regional or event-specific codes that MTGStocks
created and Scryfall may not model identically.

**Fix path:** Investigate each code on mtgstocks.com and cross-reference
with Scryfall's set list to find the canonical set code.  If a mapping
exists, add a `set_code_alias` table (future migration) or add CASE
branches in the procedure.

### 4. NULL set_abbr
Some print_ids in the MTGStocks export have no `card_set` object in their
`info.json`, so `set_abbr` is NULL after parsing.  Step 3 already guards
against this with `WHERE u.set_abbr IS NOT NULL`.

## Priority Order

1. **DD3** — highest volume; investigate whether step 2 already resolves all DD3 prints via scryfall_id.
2. **PP\* codes** — medium volume; option B (rely on step 2) is acceptable short-term.
3. **Unknown codes** — low volume; manual lookup per code.
4. **NULL set_abbr** — already filtered; verify row count is stable across runs.

## Next Steps

- [ ] Run `from_raw_to_staging` after migration 16 lands and check which of
  these sets end up with rejects (step 2 may already resolve many of them).
- [ ] For codes where step 2 fails (prints with no external IDs), apply the
  mtgstock_id backfill script (`scripts/mtgstock_backfill_identifiers.py`)
  after manually identifying the card_version_id.
- [ ] Consider migration 17 for the `PP*` → `p*` normalization if the reject
  count from pre-release promos is significant.
```

- [ ] **Step 3: Commit**

```bash
git add docs/investigate/mtgstock_missing_set_codes.md
git commit -m "docs(investigate): document 20 MTGStock set codes missing from card_catalog.sets

Includes root-cause analysis (DD3 legacy code, PP* promo convention,
unknown regional codes, NULL set_abbr) and fix paths for each category.
Most should resolve via step 2 (scryfall_id/tcg_id); DD3 and PP* codes
are the priority items."
```

---

## Self-Review Checklist

### Spec coverage
- [x] Fix `06_prices.sql` (task 1)
- [x] Create migration and apply to DB (task 2)
- [x] Script to link mtgstock_id to other identifiers (task 3)
- [x] Investigate folder for cards without collector_id (task 4)
- [x] Investigate folder for step 3 (missing set codes) (task 5)

### No placeholders
- All SQL and Python code is complete and runnable
- All commands include expected output
- No "TBD" or "fill in later" except for the table rows that require a live DB query (clearly marked)

### Type consistency
- `card_identifier_ref_id` used consistently (int, from `card_identifier_ref`)
- `card_version_id` consistently UUID
- `print_id` consistently bigint, cast to `::text` when stored as `value` in `card_external_identifier`
- `set_code` consistently lowercase in catalog; `LOWER()` applied at all join sites
