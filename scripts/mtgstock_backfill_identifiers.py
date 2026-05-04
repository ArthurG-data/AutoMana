"""
mtgstock_backfill_identifiers.py

Pre-populates card_catalog.card_external_identifier with mtgstock_id entries
for print_ids in pricing.raw_mtg_stock_price that can be resolved to a
card_version_id via scryfall_id, tcgplayer_id, or cardtrader_id.

This script does not attempt to pre-check which print_ids are already mapped
(that would require scanning 228M rows). Instead, it delegates to the actual
staging procedure (load_staging_prices_batched) which is optimized for the task.
All inserts use ON CONFLICT DO NOTHING, making the operation idempotent.

The staging procedure already back-fills mtgstock_id entries for resolved rows
(step 3e in the code). Running the full pipeline ensures complete coverage:

1. Resolved via print_id (fast path for already-mapped rows)
2. Resolved via external IDs (back-fills mtgstock_id for new mappings)
3. Resolved via set+collector (converts invalid case-sensitivity)
4. Entries to reject table for manual investigation

Usage:
    cd /home/arthur/projects/AutoMana
    ./.venv/bin/python scripts/mtgstock_backfill_identifiers.py [--dry-run]

Options:
    --dry-run   Report what would happen without modifying the DB.

Note: This script is idempotent. It creates the mtgstock_id ref if missing,
and all inserts skip conflicts. Safe to re-run at any time.
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
            logger.info("Starting mtgstock_id backfill...")

            # Step 1: Ensure mtgstock_id ref exists (idempotent)
            await conn.execute("""
                INSERT INTO card_catalog.card_identifier_ref (identifier_name)
                VALUES ('mtgstock_id')
                ON CONFLICT (identifier_name) DO NOTHING
            """)
            logger.info("mtgstock_id ref initialized")

            # Step 2: Get before count
            before_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM card_catalog.card_external_identifier cei
                WHERE cei.card_identifier_ref_id = (
                    SELECT card_identifier_ref_id
                    FROM card_catalog.card_identifier_ref
                    WHERE identifier_name = 'mtgstock_id'
                )
            """)
            logger.info("Current mtgstock_id entries: %d", before_count)

            if DRY_RUN:
                logger.info("[dry-run] Would call pricing.load_staging_prices_batched to backfill mtgstock_id")
                logger.info("[dry-run] (All inserts use ON CONFLICT DO NOTHING, so idempotent)")
                logger.info("[dry-run] Re-run without --dry-run to proceed with staging procedure")
                return

            # Step 3: Call the actual staging procedure to do the backfill
            # This is the production-grade way to resolve print_ids because:
            # - It uses the same resolution logic (step 1/2/3)
            # - It batches work to avoid memory bloat
            # - It back-fills mtgstock_id entries (step 3e)
            logger.info("Calling staging procedure (this may take several minutes for full historical backfill)...")

            await conn.execute("""
                SELECT pricing.load_staging_prices_batched('mtgstocks', 30, NULL)
            """)

            logger.info("Staging procedure completed")

            # Step 4: Get after count
            after_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM card_catalog.card_external_identifier cei
                WHERE cei.card_identifier_ref_id = (
                    SELECT card_identifier_ref_id
                    FROM card_catalog.card_identifier_ref
                    WHERE identifier_name = 'mtgstock_id'
                )
            """)
            new_entries = after_count - before_count
            logger.info("Backfill complete: added %d new mtgstock_id entries (%d → %d total)",
                       new_entries, before_count, after_count)

            if DRY_RUN:
                logger.info("[dry-run] Would insert %d rows into card_external_identifier", len(final_rows))
                for row in final_rows[:20]:
                    logger.info("  print_id=%-8s → card_version_id=%s", row["print_id"], row["card_version_id"])
                if len(final_rows) > 20:
                    logger.info("  ... and %d more", len(final_rows) - 20)
                return

            if not final_rows:
                logger.info("Nothing to backfill — all resolvable print_ids already have mtgstock_id entries.")
                return

            # Fetch the mtgstock_id ref_id once.
            ref_row = await conn.fetchrow(
                "SELECT card_identifier_ref_id FROM card_catalog.card_identifier_ref "
                "WHERE identifier_name = 'mtgstock_id' LIMIT 1"
            )
            if ref_row is None:
                raise RuntimeError("No card_identifier_ref row for 'mtgstock_id' — is the catalog seeded?")
            ref_id = ref_row["card_identifier_ref_id"]

            # Bulk-insert, ignoring already-existing PK conflicts.
            inserted = await conn.executemany(
                """
                INSERT INTO card_catalog.card_external_identifier
                    (card_identifier_ref_id, card_version_id, value)
                VALUES ($1, $2, $3)
                ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING
                """,
                [(ref_id, row["card_version_id"], str(row["print_id"])) for row in final_rows],
            )
            logger.info(
                "Backfill complete: attempted %d inserts (conflicts silently skipped). "
                "Re-run to verify idempotency.",
                len(final_rows),
            )

    finally:
        await teardown(pool)


if __name__ == "__main__":
    asyncio.run(main())
