# Productionize PriceCharting matching + staging (notebook Steps 1/4/5)

Date: 2026-05-31
Branch: `fix/2026-05-31-pricecharting-sales-parser` (continues the parser fix)

## Goal

Turn the notebook prototype's Steps 1 (set→set_code match), 4 (PC product →
card_version_id match) and 5 (stage sold rows into `pricing.ebay_scraped_sold`)
into real layered services, consuming the **service's actual JSON output**
(uid-keyed), not the notebook's stale slug-keyed format.

`promote_sold_obs` already consumes `ebay_scraped_sold` (verified prior session),
so this closes the gap between "download to JSON" and the pricing tables.

## Critical: notebook is the ALGORITHM reference, NOT the data-format reference

The parser fix changed the on-disk shape. Lift the *logic*; rewrite all file I/O
against what `scrape_sales`/`scrape_catalog` actually emit:

| | Service output (real) | Notebook assumed |
|---|---|---|
| sets file | `sets.json` = `{sets:[{uid,name}]}` | `{sets:[{slug,name,uid,url}]}` |
| catalog | `products/{uid}.json` = `{products:[{product_id,title,product_type,url,...}]}` | `products/{slug}.json` |
| sales | `sales/{uid}.json` = `{products:{pid:{tcgplayer_id, sales:[{grade,sold_at,title,price_cents,source}]}}}` | flat `sales:[{sale_date,listing_title,product_id}]` + top-level `tcgplayer_map` |

Join sets by **name** (matching is name-based anyway) → keep everything uid-keyed.
Validated: name-matcher hits **322/375 sets (85%)** on real data
(exact 273, fuzzy 21, prefix 15, override 9, suffix 4); unmatched are WC decks,
"vs" duel decks, anthologies — legit non-sets.

## Components

### Migration
- `migration_61_add_pricecharting_identifier.sql` — add `pricecharting_id` to
  `card_catalog.card_identifier_ref` (idempotent). Also add to base
  `02_card_schema.sql` VALUES list for fresh rebuilds.

### Repository methods (CQS-correct names)
- `SetReferenceRepository.fetch_sets_for_matching()` → `[(set_name, set_code)]` where `digital=false` *(query)*
- `CardReferenceRepository.fetch_versions_by_set_and_name(set_code, name)` → rows with
  card_version_id, collector_number, frame_effects, full_art, border_color_name, card_name, tcgplayer_id *(query)*
- `CardReferenceRepository.upsert_pricecharting_id(card_version_id, value)` → register PC product_id as external identifier *(command)*
- `PricingTierRepository.upsert_price_source(code, currency, name)` → source_id *(command)*
- `PricingTierRepository.upsert_source_products_for_cards(card_version_ids, source_code)` → `{cv_id: source_product_id}`
  — reuse existing `_INSERT_PRODUCTS_BATCH_SQL` / `_ENSURE_SOURCE_PRODUCT_SQL` / `_FETCH_SOURCE_PRODUCT_IDS_SQL` *(command)*

### Pure helpers (unit-tested, ported from notebook)
- `pc_matching.py`: `normalize_set_name`, `NAME_OVERRIDES`, `match_set_code`, treatment scoring, `parse_finish`
- `pc_staging.py` (or inline): `parse_condition`, `SOURCE_TO_MARKETPLACE`, `build_item_id` (`pc-`+sha1[:12])

### Services
- `pricecharting.build_match_catalog` (Steps 1+4): load sets+catalog, match sets→set_code,
  match each single→card_version_id, **register pricecharting_id external identifier** for matches,
  write `catalog.json` to storage. Repos: set + card_catalog (+ external id command).
- `pricecharting.stage_sold` (Step 5): load catalog+sales, parse condition/finish/marketplace,
  resolve source_product_ids, `insert_scraped_sold` with deterministic item_id + delete-before-insert.
  Repos: pricing + ebay_scrape.

### Wiring
- Register both services in `service_modules.py` (backend, celery, all).
- No `track_step` — match the existing scrape services' convention (flag if reviewer wants it added across all four).

## Validation discipline (advisor)
1. Set-matcher on real `sets.json` — DONE (85%).
2. Before trusting Service 2: run `scrape_sales` on ONE small set to emit a REAL
   `sales/{uid}.json`, then assert Service 2 consumes *that*, not a self-shaped fixture.
3. Match-catalog: spot-check a known card (Ragavan #138 → correct card_version_id).

## Chunks (commit each)
- A: migration + repo methods + repo/helper unit tests
- B: build_match_catalog service + pure-helper unit tests + real-data spot check
- C: stage_sold service + unit tests + real sales-file integration check

## Status — COMPLETE (3 commits)
- A `d321329d` — migration_61 + 02_card_schema seed (pricecharting_id=9); repo
  methods fetch_versions_by_set_and_name / fetch_sets_for_matching /
  upsert_price_source / upsert_source_products_for_cards. All verified vs dev DB.
- B `5b29bd26` — pc_matching.py + build_match_catalog service. **Improvement over
  notebook:** added collector-number filter (doc's Pass 1) after a real-data spot
  check exposed "[Extended Art] #315" mis-mapping to #138.
- C `be213f73` — pc_staging.py + stage_sold service. Validated against REAL
  scrape_sales output (3 live MH2 cards → 213 staged rows, correct
  marketplace/condition/cv mapping, 213 unique item_ids).
- 68 pricecharting unit tests pass; no new failures in the core+tasks suite
  (11 pre-existing env failures unchanged).

### Notes for reviewer / follow-ups
- **Idempotency divergence from notebook:** notebook did DELETE-then-insert;
  stage_sold relies on the deterministic item_id + ON CONFLICT DO NOTHING (the
  correct production idempotency; no bulk-delete primitive on the scrape repo).
- **Per-product DB query in matching:** build_match_catalog issues one
  fetch_versions_by_set_and_name per single (~63k). Fine for a batch job; could
  be batched later if it becomes a bottleneck.
- **No beat schedule yet** — both services run manually via run_service, matching
  the existing scrape services. Wire a beat chain
  (scrape_catalog → scrape_sales → build_match_catalog → stage_sold →
  promote_sold_obs) when ready to automate.
- **No track_step** — consistent with the existing scrape services (flagged).
