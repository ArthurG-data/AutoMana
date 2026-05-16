"""
backfill_listing_variants.py

Interactive backfill for ebay_active_listings rows that are missing
condition_id / finish_id / product_id (created before migration_37).

Usage:
    cd /home/arthur/projects/AutoMana
    ./.venv/bin/python scripts/backfill_listing_variants.py [--seed] [--dry-run] [--app-code CODE]

Options:
    --seed            Pull live eBay active listings first, then backfill.
    --dry-run         Print what would be saved without writing to the DB.
    --app-code CODE   Only process listings for this seller account.
"""
import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DRY_RUN = "--dry-run" in sys.argv
SEED    = "--seed"    in sys.argv
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


async def seed_from_ebay(conn, app_code_filter: str | None = None, dry_run: bool = False) -> None:
    """Pull all active eBay listings and insert new ones into ebay_active_listings."""
    from uuid import UUID
    from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
    from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository
    from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
    from automana.core.services.app_integration.ebay._auth_context import resolve_token
    from automana.core.services.app_integration.ebay.market_price_scorer import score_title
    from automana.core.QueryExecutor import AsyncQueryExecutor

    executor = AsyncQueryExecutor()
    auth_repo = EbayAuthRepository(conn, executor)
    card_repo = CardReferenceRepository(conn, executor)

    active_users = await auth_repo.get_active_app_code_users()
    if not active_users:
        print("No active eBay sellers found in the database.")
        return

    for row in active_users:
        user_id  = UUID(str(row["user_id"]))
        app_code = str(row["app_code"])
        if app_code_filter and app_code != app_code_filter:
            continue

        print(f"\033[34mFetching eBay active listings for {app_code}...\033[0m")
        token = await resolve_token(auth_repo, user_id=user_id, app_code=app_code)
        env   = await auth_repo.get_environment(app_code=app_code)
        selling_repo = EbaySellingRepository(environment=(env or "production").lower())

        seeded = skipped = unresolvable = 0
        page = 1
        while True:
            payload = {"token": token, "limit": 100, "offset": page, "marketplace_id": "15"}
            raw = await selling_repo.get_active(payload)
            active_list = (raw.get("GetMyeBaySellingResponse") or {}).get("ActiveList") or {}
            item_array  = active_list.get("ItemArray") or {}
            raw_items   = item_array.get("Item")

            if not raw_items:
                break
            if isinstance(raw_items, dict):
                raw_items = [raw_items]

            for item in raw_items:
                item_id = str(item.get("ItemID", "")).strip()
                title   = str(item.get("Title", "")).strip()
                if not item_id:
                    continue

                # Resolve card_version_id from listing title using trigram + score_title
                candidates = await card_repo.suggest(query=title, limit=10)
                best_cv: UUID | None = None
                best_score = 0.4  # lower threshold for seeding; user can re-link during backfill
                for c in candidates:
                    sc = score_title(
                        title,
                        card_name=c.get("card_name", ""),
                        set_code=c.get("set_code"),
                        is_foil=None,
                        frame=None,
                    )
                    if sc >= best_score:
                        best_score = sc
                        best_cv = UUID(str(c["card_version_id"]))

                if best_cv is None:
                    print(f"  \033[33m⚠ Unresolvable:\033[0m {title[:70]}")
                    unresolvable += 1
                    continue

                if dry_run:
                    print(f"  [dry-run] {item_id}: {title[:60]}")
                    seeded += 1
                    continue

                status = await conn.execute("""
                    INSERT INTO app_integration.ebay_active_listings
                        (item_id, app_code, card_version_id, marketplace_id)
                    VALUES ($1, $2, $3, '15')
                    ON CONFLICT (item_id) DO NOTHING
                """, item_id, app_code, str(best_cv))
                if status == "INSERT 0 1":
                    seeded += 1
                else:
                    skipped += 1

            # Pagination
            pagination   = active_list.get("PaginationResult") or {}
            total_pages  = int(pagination.get("TotalNumberOfPages") or 1)
            if page >= total_pages:
                break
            page += 1

        tag = "[dry-run] " if dry_run else ""
        print(
            f"\033[32m{tag}Seed complete for {app_code}:\033[0m "
            f"{seeded} new · {skipped} already tracked · {unresolvable} unresolvable"
        )


def _prompt(label: str, hint: str, default: str) -> str:
    """Print a coloured prompt and return stripped user input."""
    return input(f"\033[32m{label}\033[0m \033[90m{hint} (default: {default}):\033[0m ").strip()


async def _relink_flow_async(conn, card_label: str) -> tuple[str | None, str | None, str | None]:
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
    """Interactively review one listing. Returns 'saved', 'skipped', or 'quit'."""
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
    tag = "[dry-run] Would save" if DRY_RUN else "Saved"
    print(f"\033[32m{tag}\033[0m \033[90m— {cond} · {finish} · {card_label}\033[0m")
    return "saved"


async def main() -> None:
    import os
    from pathlib import Path
    from automana.tools.tui.shared import bootstrap, teardown

    # Load PGP secret from the local secrets directory when running outside Docker.
    pgp_file = Path(__file__).resolve().parents[1] / "config" / "secrets" / "pgp_secret_key.txt"
    if pgp_file.exists() and not os.environ.get("PGP_SECRET_KEY"):
        os.environ["PGP_SECRET_KEY"] = pgp_file.read_text().strip()

    pool = await bootstrap()
    try:
        async with pool.acquire() as conn:
            if SEED:
                await seed_from_ebay(conn, app_code_filter=APP_CODE, dry_run=DRY_RUN)
                if DRY_RUN:
                    return

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


if __name__ == "__main__":
    asyncio.run(main())
