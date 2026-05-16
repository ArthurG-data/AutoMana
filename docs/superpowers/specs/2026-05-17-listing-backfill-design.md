# Design: Interactive eBay Listing Variant Backfill

## Context

Migration 37 added `condition_id`, `finish_id`, `product_id`, `language_id`, and `marketplace_id`
to `app_integration.ebay_active_listings`. Rows created before the migration have NULL in all these
columns. This tool lets the user review each unlinked listing, confirm or correct the card match,
set condition + finish, and write the values back — one listing at a time.

## Approach

Standalone Python script in `/scripts/` using `bootstrap()` / `teardown()` from
`automana.tools.tui.shared` (same pattern as `scripts/mtgstock_backfill_identifiers.py`).
Not a registered service — interactivity doesn't fit the service registry's call convention.

## Script

**File:** `scripts/backfill_listing_variants.py`

**Run:**
```bash
./.venv/bin/python scripts/backfill_listing_variants.py
./.venv/bin/python scripts/backfill_listing_variants.py --dry-run
./.venv/bin/python scripts/backfill_listing_variants.py --app-code MY_STORE
```

**Flags:**
- `--dry-run` — print what would be saved, no DB writes
- `--app-code CODE` — filter to one seller account

## Functions

| Function | Signature | Does |
|---|---|---|
| `fetch_pending` | `(conn, app_code=None) -> list[dict]` | SELECT from `ebay_active_listings WHERE condition_id IS NULL`, joined to card name + set code + collector_number |
| `search_cards` | `(conn, query: str) -> list[dict]` | Full-text search via `card_catalog.v_cards_by_name`, returns up to 8 rows: card_version_id, card_name, set_name, set_code, collector_number |
| `save_variant` | `(conn, item_id, card_version_id, condition_code, finish_code, dry_run) -> None` | Runs ensure_product then UPDATE on `ebay_active_listings` |

## Interactive Loop (per listing)

```
── Listing N / Total ──────────────────────────────────
Item ID    <item_id>
Card       <card_name>
Set        <set_name> (<set_code>) · #<collector_number>
Listed     <listed_at date>  (eBay <marketplace_id or AU>)

Condition  [NM / LP / MP / HP / DMG] (default: NM): _
Finish     [nonfoil / foil / etched / ...] (default: nonfoil): _
Card OK?   [y / r=re-link] (default: y): _

✓ Saved — <condition> · <finish> · <card_name> (<set_code> #<num>)
```

**Input rules:**
- Enter at any prompt accepts the shown default
- Prefix matching: `m` → MP, `fo` → foil, `n` → NM
- `s` at any prompt: skip this listing (no write)
- `q` at any prompt: quit, print summary, exit

**Re-link sub-flow** (triggered by `r` at Card OK? prompt):
```
Search card name: <user types partial name, min 2 chars>
[1] Card Name — Set Name (CODE) · #num
[2] ...
[0] Cancel (keep original)
Pick: _
→ Relinked to Card Name — Set (CODE) · #num
```

Up to 8 matches shown. Picking `0` cancels and keeps the original `card_version_id`.
If the search returns 0 results, print `No matches — try a different name.` and re-prompt the search.

## DB writes on save

Two sequential statements on the same connection (no wrapping transaction — partial saves are acceptable for a backfill):

**1. ensure_product** — mirrors `sales_queries.ENSURE_PRODUCT`:
```sql
WITH new_product AS (
    INSERT INTO pricing.product_ref (game_id)
    SELECT 1 WHERE NOT EXISTS (
        SELECT 1 FROM pricing.mtg_card_products WHERE card_version_id = $1
    ) RETURNING product_id
), link AS (
    INSERT INTO pricing.mtg_card_products (product_id, card_version_id)
    SELECT product_id, $1 FROM new_product ON CONFLICT (card_version_id) DO NOTHING
)
SELECT product_id FROM pricing.mtg_card_products WHERE card_version_id = $1;
```

**2. update listing row:**
```sql
UPDATE app_integration.ebay_active_listings SET
    card_version_id = $2,
    product_id      = $3,
    condition_id    = (SELECT condition_id FROM pricing.card_condition    WHERE UPPER(code) = UPPER($4)),
    finish_id       = (SELECT finish_id   FROM card_catalog.card_finished WHERE UPPER(code) = UPPER($5)),
    language_id     = card_catalog.default_language_id(),
    marketplace_id  = COALESCE(marketplace_id, '15')
WHERE item_id = $1;
```

`marketplace_id` uses `COALESCE` — preserves any existing value, defaults to AU (`'15'`) only if still NULL.

## End-of-run summary

```
Done. 5 updated · 2 skipped · 1 remaining.
```

## Verification

1. Run with `--dry-run` — confirm all listings print correctly, no DB changes
2. Run without flag on one listing — confirm row in `ebay_active_listings` has all 5 columns populated
3. Test re-link — confirm `card_version_id` changes and `product_id` reflects the new card
4. Test `q` mid-run — confirm partial results are saved, summary shows remaining count
5. Test `--app-code` filter — confirm only listings for that account appear
