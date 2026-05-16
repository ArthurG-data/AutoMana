# Listing Variant Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/backfill_listing_variants.py` — an interactive terminal script that walks through `ebay_active_listings` rows with NULL condition_id, lets the user confirm or correct the card match, set condition + finish, and writes the values back one listing at a time.

**Architecture:** Single asyncpg script matching the `scripts/mtgstock_backfill_identifiers.py` pattern. Uses `bootstrap()` / `teardown()` from `automana.tools.tui.shared`. Three async DB helpers (`fetch_pending`, `search_cards`, `save_variant`) plus pure input-parsing helpers that are unit-tested independently. Interactive loop uses `input()` synchronously between async DB calls.

**Tech Stack:** Python 3.11+, asyncpg, `automana.tools.tui.shared.bootstrap`, pytest + pytest-asyncio for tests.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/backfill_listing_variants.py` | **Create** | Full script: arg parsing, DB helpers, interactive loop, `main()` |
| `tests/unit/scripts/test_backfill_listing_variants.py` | **Create** | Unit tests for pure helpers `_parse_condition`, `_parse_finish` |

---

## Task 1: Unit tests for input-parsing helpers

These two pure functions will be imported into the test file directly. Write them first so the test guides the implementation.

**Files:**
- Create: `tests/unit/scripts/__init__.py` (empty)
- Create: `tests/unit/scripts/test_backfill_listing_variants.py`

- [ ] **Step 1: Create empty `__init__.py`**

```bash
touch tests/unit/scripts/__init__.py
```

- [ ] **Step 2: Write the test file**

```python
# tests/unit/scripts/test_backfill_listing_variants.py
"""Unit tests for pure input-parsing helpers in backfill_listing_variants."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))

from backfill_listing_variants import _parse_condition, _parse_finish


# ── _parse_condition ──────────────────────────────────────────────────────────

def test_parse_condition_empty_returns_default():
    assert _parse_condition("", "NM") == "NM"

def test_parse_condition_exact_match_case_insensitive():
    assert _parse_condition("lp", "NM") == "LP"
    assert _parse_condition("LP", "NM") == "LP"

def test_parse_condition_prefix_match():
    assert _parse_condition("m", "NM") == "MP"   # MP before HP alphabetically… wait: NM,LP,MP,HP,DMG
    # "m" matches both MP and (no) — MP is the only one starting with M
    assert _parse_condition("h", "NM") == "HP"
    assert _parse_condition("d", "NM") == "DMG"
    assert _parse_condition("n", "NM") == "NM"

def test_parse_condition_invalid_returns_none():
    assert _parse_condition("xyz", "NM") is None

def test_parse_condition_ambiguous_returns_none():
    # nothing starts with "z" — returns None
    assert _parse_condition("z", "NM") is None


# ── _parse_finish ─────────────────────────────────────────────────────────────

def test_parse_finish_empty_returns_default():
    assert _parse_finish("", "NONFOIL") == "NONFOIL"

def test_parse_finish_exact_match_case_insensitive():
    assert _parse_finish("foil", "NONFOIL") == "FOIL"
    assert _parse_finish("FOIL", "NONFOIL") == "FOIL"

def test_parse_finish_prefix_nonfoil():
    assert _parse_finish("non", "NONFOIL") == "NONFOIL"
    assert _parse_finish("n", "NONFOIL") == "NONFOIL"

def test_parse_finish_prefix_foil():
    assert _parse_finish("fo", "NONFOIL") == "FOIL"

def test_parse_finish_prefix_etched():
    assert _parse_finish("e", "NONFOIL") == "ETCHED"

def test_parse_finish_ambiguous_returns_none():
    # both FOIL and (no other) — "f" uniquely matches FOIL since NONFOIL starts with N
    assert _parse_finish("f", "NONFOIL") == "FOIL"

def test_parse_finish_invalid_returns_none():
    assert _parse_finish("zzz", "NONFOIL") is None
```

- [ ] **Step 3: Run tests — expect ImportError (file doesn't exist yet)**

```bash
cd /home/arthur/projects/AutoMana
./.venv/bin/pytest tests/unit/scripts/test_backfill_listing_variants.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'backfill_listing_variants'`

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/unit/scripts/__init__.py tests/unit/scripts/test_backfill_listing_variants.py
git commit -m "test: add unit tests for backfill_listing_variants parsing helpers"
```

---

## Task 2: Implement the parsing helpers + skeleton script

**Files:**
- Create: `scripts/backfill_listing_variants.py`

- [ ] **Step 1: Create the script with the two pure helpers**

```python
"""
backfill_listing_variants.py

Interactive backfill for ebay_active_listings rows that are missing
condition_id / finish_id / product_id (created before migration_37).

Usage:
    cd /home/arthur/projects/AutoMana
    ./.venv/bin/python scripts/backfill_listing_variants.py [--dry-run] [--app-code CODE]

Options:
    --dry-run         Print what would be saved without writing to the DB.
    --app-code CODE   Only process listings for this seller account.
"""
import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DRY_RUN = "--dry-run" in sys.argv
APP_CODE: str | None = None
for _i, _a in enumerate(sys.argv):
    if _a == "--app-code" and _i + 1 < len(sys.argv):
        APP_CODE = sys.argv[_i + 1]

_CONDITIONS = ["NM", "LP", "MP", "HP", "DMG"]
_FINISHES   = ["NONFOIL", "FOIL", "ETCHED", "SURGE_FOIL", "RIPPLE_FOIL", "RAINBOW_FOIL"]


def _parse_condition(raw: str, default: str) -> str | None:
    """Parse user input to a condition code. Empty → default. Prefix match → code. No match → None."""
    text = raw.strip().upper()
    if not text:
        return default
    matches = [c for c in _CONDITIONS if c.startswith(text)]
    return matches[0] if len(matches) == 1 else None


def _parse_finish(raw: str, default: str) -> str | None:
    """Parse user input to a finish code. Empty → default. Prefix match → code. No match → None."""
    text = raw.strip().upper()
    if not text:
        return default
    matches = [f for f in _FINISHES if f.startswith(text)]
    return matches[0] if len(matches) == 1 else None


async def main() -> None:
    print("(placeholder — not yet implemented)")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run tests — expect PASS**

```bash
cd /home/arthur/projects/AutoMana
./.venv/bin/pytest tests/unit/scripts/test_backfill_listing_variants.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_listing_variants.py
git commit -m "feat: add backfill_listing_variants skeleton with parsing helpers"
```

---

## Task 3: Implement `fetch_pending` and `search_cards`

**Files:**
- Modify: `scripts/backfill_listing_variants.py`

- [ ] **Step 1: Add the two DB query helpers below `_parse_finish`**

```python
async def fetch_pending(conn, app_code: str | None = None) -> list[dict]:
    """Return all ebay_active_listings rows missing condition_id, joined to card info."""
    where = "WHERE eal.condition_id IS NULL"
    params = []
    if app_code:
        where += " AND eal.app_code = $1"
        params.append(app_code)

    rows = await conn.fetch(f"""
        SELECT
            eal.item_id,
            eal.app_code,
            eal.listed_at,
            eal.marketplace_id,
            eal.card_version_id,
            ucr.card_name,
            s.set_name,
            s.set_code,
            cv.collector_number
        FROM app_integration.ebay_active_listings eal
        JOIN card_catalog.card_version cv
            ON cv.card_version_id = eal.card_version_id
        JOIN card_catalog.unique_cards_ref ucr
            ON ucr.unique_card_id = cv.unique_card_id
        JOIN card_catalog.sets s
            ON s.set_id = cv.set_id
        {where}
        ORDER BY eal.listed_at
    """, *params)
    return [dict(r) for r in rows]


async def search_cards(conn, query: str) -> list[dict]:
    """Search card versions by partial name. Returns up to 8 matches."""
    rows = await conn.fetch("""
        SELECT
            cv.card_version_id,
            ucr.card_name,
            s.set_name,
            s.set_code,
            cv.collector_number
        FROM card_catalog.card_version cv
        JOIN card_catalog.unique_cards_ref ucr
            ON ucr.unique_card_id = cv.unique_card_id
        JOIN card_catalog.sets s
            ON s.set_id = cv.set_id
        WHERE ucr.card_name ILIKE $1
        ORDER BY ucr.card_name, s.set_code, cv.collector_number
        LIMIT 8
    """, f"%{query}%")
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Run tests — still PASS (no logic changed)**

```bash
./.venv/bin/pytest tests/unit/scripts/test_backfill_listing_variants.py -v
```

Expected: all 12 PASS.

- [ ] **Step 3: Smoke-test queries against dev DB**

```bash
./.venv/bin/python - <<'EOF'
import asyncio
from automana.tools.tui.shared import bootstrap, teardown
import sys; sys.argv = ["x"]  # prevent DRY_RUN/APP_CODE parsing
sys.path.insert(0, "scripts")
from backfill_listing_variants import fetch_pending, search_cards

async def run():
    pool = await bootstrap()
    async with pool.acquire() as conn:
        pending = await fetch_pending(conn)
        print(f"Pending rows: {len(pending)}")
        results = await search_cards(conn, "lightning bolt")
        for r in results:
            print(f"  {r['card_name']} — {r['set_code']} #{r['collector_number']}")
    await teardown(pool)

asyncio.run(run())
EOF
```

Expected: `Pending rows: 0` + 8 Lightning Bolt printings listed.

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_listing_variants.py
git commit -m "feat: add fetch_pending and search_cards DB helpers to backfill script"
```

---

## Task 4: Implement `save_variant`

**Files:**
- Modify: `scripts/backfill_listing_variants.py`

- [ ] **Step 1: Add `save_variant` below `search_cards`**

```python
async def save_variant(
    conn,
    item_id: str,
    card_version_id: str,
    condition_code: str,
    finish_code: str,
    dry_run: bool = False,
) -> None:
    """Ensure product exists then update the listing row with variant info."""
    if dry_run:
        print(f"  [dry-run] Would save {condition_code} · {finish_code} for item {item_id}")
        return

    # 1. Ensure product_ref + mtg_card_products exist for this card version
    product_id = await conn.fetchval("""
        WITH new_product AS (
            INSERT INTO pricing.product_ref (game_id)
            SELECT 1
            WHERE NOT EXISTS (
                SELECT 1 FROM pricing.mtg_card_products WHERE card_version_id = $1
            )
            RETURNING product_id
        ),
        link AS (
            INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
            SELECT product_id, $1 FROM new_product
            ON CONFLICT (card_version_id) DO NOTHING
        )
        SELECT product_id FROM pricing.mtg_card_products WHERE card_version_id = $1
    """, card_version_id)

    # 2. Update the listing row
    await conn.execute("""
        UPDATE app_integration.ebay_active_listings SET
            card_version_id = $2,
            product_id      = $3,
            condition_id    = (SELECT condition_id FROM pricing.card_condition
                               WHERE UPPER(code) = UPPER($4)),
            finish_id       = (SELECT finish_id FROM card_catalog.card_finished
                               WHERE UPPER(code) = UPPER($5)),
            language_id     = card_catalog.default_language_id(),
            marketplace_id  = COALESCE(marketplace_id, '15')
        WHERE item_id = $1
    """, item_id, card_version_id, product_id, condition_code, finish_code)
```

- [ ] **Step 2: Run unit tests — still PASS**

```bash
./.venv/bin/pytest tests/unit/scripts/test_backfill_listing_variants.py -v
```

Expected: all 12 PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_listing_variants.py
git commit -m "feat: add save_variant DB helper to backfill script"
```

---

## Task 5: Implement the interactive loop and `main()`

**Files:**
- Modify: `scripts/backfill_listing_variants.py`

- [ ] **Step 1: Replace the placeholder `main()` with the full implementation**

```python
def _prompt(label: str, hint: str, default: str) -> str:
    """Print a coloured prompt and return stripped user input."""
    return input(f"\033[32m{label}\033[0m \033[90m{hint} (default: {default}):\033[0m ").strip()


def _relink_flow(conn_sync_ref) -> tuple[str | None, str | None, str | None]:
    """
    Returns (card_version_id_str, card_name, set_label) or (None, None, None) if cancelled.
    conn_sync_ref is a list[conn] so the async caller can swap it in.
    """
    # This is called from inside an async context but uses asyncio.get_event_loop().run_until_complete
    # — instead, we return a coroutine that the caller awaits.
    raise NotImplementedError("use _relink_flow_async")


async def _relink_flow_async(conn, loop_label: str) -> tuple[str | None, str | None, str | None]:
    """Interactive card search. Returns (card_version_id str, card_name, set_label) or Nones."""
    while True:
        query = input("\033[90m  Search card name:\033[0m ").strip()
        if len(query) < 2:
            print("  Enter at least 2 characters.")
            continue
        results = await search_cards(conn, query)
        if not results:
            print("  No matches — try a different name.")
            continue
        for i, r in enumerate(results, 1):
            print(f"  \033[34m[{i}]\033[0m {r['card_name']} — {r['set_name']} ({r['set_code']}) · #{r['collector_number']}")
        print("  \033[90m[0] Cancel re-link\033[0m")
        pick = input("\033[90m  Pick:\033[0m ").strip()
        if pick == "0":
            return None, None, None
        if pick.isdigit() and 1 <= int(pick) <= len(results):
            r = results[int(pick) - 1]
            label = f"{r['card_name']} ({r['set_code']} #{r['collector_number']})"
            print(f"  \033[32m→ Relinked to {label}\033[0m")
            return str(r["card_version_id"]), r["card_name"], label
        print(f"  Invalid choice — enter a number between 0 and {len(results)}.")


async def _review_listing(conn, row: dict, idx: int, total: int) -> str:
    """
    Interactively review one listing. Returns 'saved', 'skipped', or 'quit'.
    """
    listed = row["listed_at"].strftime("%Y-%m-%d") if row["listed_at"] else "?"
    market = row.get("marketplace_id") or "AU"
    set_label = f"{row['set_name']} ({row['set_code']}) · #{row['collector_number']}"

    print(f"\n\033[90m── Listing {idx} / {total} {'─' * 40}\033[0m")
    print(f"\033[90m{'Item ID':<12}\033[0m {row['item_id']}")
    print(f"\033[90m{'Card':<12}\033[0m \033[33m{row['card_name']}\033[0m")
    print(f"\033[90m{'Set':<12}\033[0m {set_label}")
    print(f"\033[90m{'Listed':<12}\033[0m {listed}  (eBay {market})")

    card_version_id = str(row["card_version_id"])
    card_label = f"{row['card_name']} ({row['set_code']} #{row['collector_number']})"

    # --- condition ---
    while True:
        raw = _prompt("Condition", "[NM / LP / MP / HP / DMG]", "NM")
        if raw.lower() == "s":
            return "skipped"
        if raw.lower() == "q":
            return "quit"
        cond = _parse_condition(raw, "NM")
        if cond:
            break
        print(f"  Unrecognised condition '{raw}' — try NM, LP, MP, HP, or DMG.")

    # --- finish ---
    while True:
        raw = _prompt("Finish   ", "[nonfoil / foil / etched / ...]", "nonfoil")
        if raw.lower() == "s":
            return "skipped"
        if raw.lower() == "q":
            return "quit"
        finish = _parse_finish(raw, "NONFOIL")
        if finish:
            break
        print(f"  Unrecognised finish '{raw}' — try nonfoil, foil, or etched.")

    # --- card OK? ---
    while True:
        raw = _prompt("Card OK? ", "[y / r=re-link]", "y").lower()
        if raw == "s":
            return "skipped"
        if raw == "q":
            return "quit"
        if raw in ("", "y"):
            break
        if raw == "r":
            new_cv, new_name, new_label = await _relink_flow_async(conn, card_label)
            if new_cv:
                card_version_id = new_cv
                card_label = new_label
            break
        print("  Enter y to confirm or r to re-link.")

    await save_variant(conn, row["item_id"], card_version_id, cond, finish, dry_run=DRY_RUN)
    tag = "[dry-run] Would save" if DRY_RUN else "✓ Saved"
    print(f"\033[32m{tag}\033[0m \033[90m— {cond} · {finish} · {card_label}\033[0m")
    return "saved"


async def main() -> None:
    from automana.tools.tui.shared import bootstrap, teardown

    pool = await bootstrap()
    try:
        async with pool.acquire() as conn:
            rows = await fetch_pending(conn, APP_CODE)
            total = len(rows)
            if total == 0:
                print("No listings with missing condition/finish found. Nothing to do.")
                return

            flag = " [DRY RUN]" if DRY_RUN else ""
            print(f"\033[34mFound {total} listing(s) with missing condition/finish. Starting backfill...{flag}\033[0m")
            print("\033[90mCommands: Enter=accept default · s=skip · q=quit · r=re-link card\033[0m")

            updated = skipped = 0
            for idx, row in enumerate(rows, 1):
                outcome = await _review_listing(conn, row, idx, total)
                if outcome == "saved":
                    updated += 1
                elif outcome == "skipped":
                    skipped += 1
                elif outcome == "quit":
                    break

            remaining = total - updated - skipped
            print(f"\n\033[32mDone. {updated} updated · {skipped} skipped · {remaining} remaining.\033[0m")
    finally:
        await teardown(pool)
```

- [ ] **Step 2: Run unit tests — still PASS**

```bash
./.venv/bin/pytest tests/unit/scripts/test_backfill_listing_variants.py -v
```

Expected: all 12 PASS.

- [ ] **Step 3: Syntax check**

```bash
./.venv/bin/python -m py_compile scripts/backfill_listing_variants.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_listing_variants.py
git commit -m "feat: complete backfill_listing_variants interactive loop and main()"
```

---

## Task 6: Smoke test end-to-end

- [ ] **Step 1: Run with `--dry-run` against dev DB**

```bash
cd /home/arthur/projects/AutoMana
./.venv/bin/python scripts/backfill_listing_variants.py --dry-run
```

Expected: `No listings with missing condition/finish found. Nothing to do.` (table is currently empty — that's correct).

- [ ] **Step 2: Insert a test row and re-run**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
INSERT INTO app_integration.ebay_active_listings (item_id, app_code, card_version_id)
SELECT '999999999999', 'TEST', card_version_id
FROM card_catalog.card_version LIMIT 1
ON CONFLICT DO NOTHING;
"
```

Then run:
```bash
./.venv/bin/python scripts/backfill_listing_variants.py --dry-run
```

Expected: shows the test listing with card name, prompts for condition/finish, prints `[dry-run] Would save`.

- [ ] **Step 3: Run without `--dry-run`, confirm, check DB**

```bash
./.venv/bin/python scripts/backfill_listing_variants.py
```

Type `NM` → `foil` → `y` → confirm.

Then verify:
```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT item_id, condition_id, finish_id, product_id, marketplace_id
FROM app_integration.ebay_active_listings
WHERE item_id = '999999999999';
"
```

Expected: all five columns populated (non-NULL).

- [ ] **Step 4: Clean up test row**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
DELETE FROM app_integration.ebay_active_listings WHERE item_id = '999999999999';
"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: backfill_listing_variants smoke-tested and complete"
```