# Decommission eBay External Sold-Price Scraper

**Date:** 2026-05-31
**Branch:** `chore/2026-05-31-decommission-ebay-sold-scraper` (off `dev`)
**Trigger:** eBay has deprecated/deprioritized the Finding API `findCompletedItems` (sold/completed-items) endpoint. Every service built on it is permanently non-viable — confirmed in dev: `scrape_global_market` runs nightly and fails *every* card×marketplace call (a Redis-config bug masks it, but even fixed it would hit a dead API), producing zero rows for all of EBAY-US / EBAY-AU / EBAY-ENCA.

## Scope decision

**Full removal** of the dead Finding-API sold-scraping family. Preserve the live Fulfillment-API own-sales path and anything shared.

### Remove (dead — depend on `find_completed_items`)
| Item | Path |
|---|---|
| Service `scrape_global_market` | `core/services/app_integration/ebay/scrape_global_market_service.py` |
| Service `category_sweep` | `core/services/app_integration/ebay/category_sweep_service.py` |
| Service `scrape_sold` (external sold) | `core/services/app_integration/ebay/scrape_sold_service.py` |
| Service `refresh_scrape_targets` | `core/services/app_integration/ebay/refresh_scrape_targets_service.py` |
| Quota helper (dead-only) | `core/services/app_integration/ebay/ebay_api_quota.py` |
| Title parser (dead-only) | `core/services/app_integration/ebay/title_parser.py` |
| Finding API repo | `core/repositories/app_integration/ebay/ApiFinding_repository.py` |
| Celery tasks | `ebay_scrape_external_sold_task`, `ebay_category_sweep_task` (+ noqa imports) in `worker/tasks/ebay.py` |
| Beat entries (4) | `ebay-scrape-external-sold-nightly`, `ebay-category-sweep-daily`, `ebay-refresh-scrape-targets-nightly`, `ebay-scrape-global-market-nightly` |
| Wiring | `ebay_finding` registration in `core/framework/wiring.py` |
| Migration | DROP `pricing.ebay_scrape_targets` (orphaned once refresh + scraper gone) |
| Tests | `test_scrape_global_market_service`, `test_category_sweep_service`, `test_scrape_sold_service`, `test_refresh_scrape_targets_service`, `test_title_parser`, `test_api_finding_pagination`, `test_finding_repository`, integration `test_category_sweep` |
| Doc | `docs/pipelines/EBAY_GLOBAL_MARKET_SCRAPER.md` (delete) + remove its row from `CLAUDE.md` |

### Modify
- **`worker/tasks/ebay.py`** — remove the two dead tasks + their module imports; keep `ebay_sync_own_sales_task` and `ebay_cleanup_raw_files_task`.

### DO NOT modify — `promote_sold_obs` stays fully intact (both channels)
Revised after review. Evidence the scrape channel is a **live promoter**, not dead code:
- `pricing.ebay_scraped_sold` holds 1086 `TCGPLAYER` rows written **05-26→05-29** (recurring, this week), all `promoted_to_obs = true`.
- `GET_UNPROMOTED_SCRAPED` is **unfiltered by marketplace** (`WHERE promoted_to_obs = false AND source_product_id IS NOT NULL`), and `promote_sold_obs` is the **only** code that flips `promoted_to_obs` → it is what promotes TCGPLAYER rows into `price_observation`.
- The live TCGPLAYER writer is **external/manual** (the only `insert_scraped_sold` callers are the three dead services, none of which write `"TCGPLAYER"`) — so it is NOT in the removal set, and removing the dead Finding services does not touch it.
- Stripping the channel would silently kill TCGPlayer → `price_observation` promotion — the exact pricing path `#346` just hardened. Keeping it intact has zero downside (all its deps are already on the keep-list).

**Follow-up (out of scope):** identify the external/manual TCGPLAYER writer of `ebay_scraped_sold` and either document or formalize it. File as a ticket.

## Post-implementation notes
- **TCGPLAYER-writer question — resolved during the docs sweep.** `docs/pipelines/PRICECHARTING_PIPELINE.md` documents that the PriceCharting pipeline replaced the Finding API (decommissioned Feb 2025) and **writes into the same `pricing.ebay_scraped_sold` table**, relying on `promote_sold_obs` to promote rows into `price_observation`. This is the live consumer relationship that made keeping `promote_sold_obs` intact correct. (Exact `TCGPLAYER` marketplace-tag writer — PriceCharting vs open_tcg — left as a minor confirm.)
- **`fetch_fx_rates` is registered in the `backend` + `all` service lists but NOT `celery`**, so the nightly `run_service` beat job cannot resolve it on the worker — the `fx_rates` table will not actually refresh. Pre-existing bug, **left untouched** (out of scope). The kept beat entry's comment is neutral ("retained for future use"), not a freshness claim.
- **Docs sweep done:** deleted the root duplicate `docs/EBAY_GLOBAL_MARKET_SCRAPER.md`, removed the `docs/README.md` index row, marked C3/P4/P5/P6/P8 MOOT in `MASTER_TECHNICAL_DEBT.md`, dropped the C3 item from `BACKLOG.md`, and fixed the stale `scrape_global_market_service` reference in `SCHEMA_NORMALIZATION_PLAN.md`. Historical `plans/` + `specs/` left as-is (immutable records).
- **Test baseline:** pre-existing pydantic/env collection failures under `tests/unit/api`, `tests/unit/core/ai`, `tests/unit/core/routers/ebay/test_build_and_create_tracking.py` reproduce identically on clean `origin/dev` (verified via stash baseline) — unrelated to this change.

### Keep (explicit)
- `pricing.fx_rates` **table** — per user instruction ("keep the fx_rate table for now").
- `fetch_fx_rates` service + `pricing-fetch-fx-rates-nightly` beat — so the kept table stays fresh (proposed; awaiting confirmation — user only asked to keep the table).
- `ebay_sync_own_sales` (Fulfillment API) + its beat.
- `promote_sold_obs` (own-sales channel only) + its beat.
- `ebay_cleanup_raw_files_task` + `ebay_raw_io.get_ebay_raw_dir` (cleanup task uses it).
- `market_price_scorer` (used by live `market_price_service` + `sync_own_sales`), `market_price_service`.
- `pricing.ebay_scraped_sold` **table** — has historical data + unexplained `TCGPLAYER` rows with no current writer; do NOT drop.
- **`EbayScrapeSoldRepository` + `ebay_scrape_queries`** — KEEP as the valid access layer for the preserved `ebay_scraped_sold` table (decision: removing the access layer while keeping the table is incoherent; keeping a wired-but-idle repo is harmless). Flag for a later decision if the table is eventually dropped.

## Safety analysis
- **TCG pipeline:** does NOT write `ebay_scraped_sold` or call `promote_sold_obs` (grep clean) → stripping the scrape channel breaks nothing live.
- **`promote_sold_obs` readers:** only the beat entry → safe to slim.
- **Shared modules:** `market_price_scorer` / `market_price_service` are live → keep. `title_parser` / `ebay_api_quota` are dead-only → remove.
- Baseline before changes: affected unit tests **289 passed**.

## Execution order
1. Remove dead services + helpers (`ebay_api_quota`, `title_parser`) + Finding repo + their tests.
2. Remove dead tasks + imports in `worker/tasks/ebay.py` (keep own-sales + cleanup tasks).
3. Remove 4 beat entries; unwire `ebay_finding`. (`promote_sold_obs` untouched.)
4. Migration: DROP `pricing.ebay_scrape_targets`.
5. Docs: delete scraper doc + CLAUDE.md row.
6. Run the **full** test suite green (wiring changes ripple); grep for dangling `ebay_finding` / removed-service references.
7. PR to `dev`.
