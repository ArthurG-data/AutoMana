# AutoMana Pipeline Technical Debt

Auto-updated by `/pipeline-health-check` after each run.
`fix_notes` and `status` fields may be edited manually — the script preserves them across updates.

<!-- DEBT_METADATA_START
last_updated: 2026-04-30T10:36:27Z
total_findings: 36
DEBT_METADATA_END -->

---

## Open Issues — Errors (20)

<!-- DEBT_ITEM_START key="pricing_run_diff::run_metadata" -->
### run_metadata · pricing_run_diff
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: {}
- **Fix**: Re-run `mtgStock_download_pipeline` after Fix 2 + Fix 3 are applied.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgjson_run_diff::run_metadata" -->
### run_metadata · mtgjson_run_diff
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: {}
- **Fix**: Trigger `daily_mtgjson_data_pipeline` via Celery or `automana-run`.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.card_coverage.card_versions_with_any_price" -->
### pricing.card_coverage.card_versions_with_any_price · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'TimeoutError: ', 'description': 'Count of card_versions with at least one price_observation (any finish).', 'category': 'volume'}
- **Fix**: Rewrite `pricing_report` SQL to avoid full hypertable scans — use `pg_class.reltuples` for row estimates, `pg_constraint` for PK checks, and time-bounded CTEs with short windows. Alternatively raise `/dev/shm` in `docker-compose.dev.yml` via `shm_size: 512m`.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.card_coverage.card_versions_with_foil_price" -->
### pricing.card_coverage.card_versions_with_foil_price · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'Count of card_versions with at least one foil (FOIL/ETCHED
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.card_coverage.card_versions_with_nonfoil_price" -->
### pricing.card_coverage.card_versions_with_nonfoil_price · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'Count of card_versions with at least one NONFOIL price obs
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.card_coverage.card_versions_without_price" -->
### pricing.card_coverage.card_versions_without_price · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'Count of card_versions with zero price observations.', 'ca
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.card_coverage.catalog_coverage_pct" -->
### pricing.card_coverage.catalog_coverage_pct · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': '% of card_versions in card_catalog that have at least one
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.card_coverage.total_observation_rows" -->
### pricing.card_coverage.total_observation_rows · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'Estimated total rows in pricing.price_observation (via pg_
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.coverage.min_per_source_observation_coverage_pct" -->
### pricing.coverage.min_per_source_observation_coverage_pct · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'MIN across sources of % of source_product rows with a pric
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.duplicate_detection.observation_duplicates_on_pk" -->
### pricing.duplicate_detection.observation_duplicates_on_pk · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'Composite-PK violations in price_observation (should alway
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.freshness.max_per_source_lag_hours" -->
### pricing.freshness.max_per_source_lag_hours · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'Hours since the latest observation per source. Headline =
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.freshness.price_observation_max_age_days" -->
### pricing.freshness.price_observation_max_age_days · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'Days since the most recent pricing.price_observation.ts_da
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.referential.observation_without_source_product" -->
### pricing.referential.observation_without_source_product · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'pricing.price_observation rows whose source_product_id no
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.referential.product_without_mtg_card_products" -->
### pricing.referential.product_without_mtg_card_products · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'pricing.product_ref rows with game=mtg but no mtg_card_pro
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_report::pricing.staging.stg_price_observation_residual_count" -->
### pricing.staging.stg_price_observation_residual_count · pricing_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block', 'description': 'Estimated row count of stg_price_observation (should drain
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgstock_report::mtgstock.cards_linked_to_card_version" -->
### mtgstock.cards_linked_to_card_version · mtgstock_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: {'description': 'Staged rows successfully resolved to a card_version_id.', 'category': 'volume'}
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgstock_report::mtgstock.cards_rejected" -->
### mtgstock.cards_rejected · mtgstock_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 6090227
- **Details**: {'description': 'Rows that failed card_version resolution and landed in the reject table.', 'category': 'health'}
- **Fix**: Fix 2 — art-card set-code + name mapping (~680K rows). Fix 3 — token resolution via `mtgstock_token_set_map` (~3.8M rows). Remaining ~1.3M require scryfall-side investigation.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgstock_report::mtgstock.link_rate_pct" -->
### mtgstock.link_rate_pct · mtgstock_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0.0
- **Details**: {'linked': 0, 'rejected': 6090227, 'denominator': 6090227, 'description': '% of staged rows (linked + rejected) that resolved to a card_version_id.', 'category': 'health'}
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgstock_report::mtgstock.pipeline_duration_seconds" -->
### mtgstock.pipeline_duration_seconds · mtgstock_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 40228.3657
- **Details**: {'ingestion_run_id': 4, 'started_at': '2026-04-28 21:38:53.715608+00:00', 'ended_at': '2026-04-29 08:49:22.081308+00:00', 'description': 'Wall-clock duration of the most recent mtgStock pipeline run.'
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgstock_report::mtgstock.rows_promoted_to_price_observation" -->
### mtgstock.rows_promoted_to_price_observation · mtgstock_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: None
- **Details**: {'exception': 'TimeoutError: ', 'description': "Rows promoted to pricing.price_observation inside the run's wall-clock window.", 'category': 'volume'}
- **Fix**: Replace the direct hypertable scan with a batch-counter approach reading from `ops.ingestion_step_batches.items_ok` for the promote step, or raise Docker shm limit.
- **Status**: open
<!-- DEBT_ITEM_END -->

---

## Open Issues — Warnings (10)

<!-- DEBT_ITEM_START key="pricing_run_diff::batch_steps" -->
### batch_steps · pricing_run_diff
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: {'per_step': None, 'total_batches': 0, 'total_bytes_mb': None, 'total_items_ok': None, 'total_duration_s': None, 'total_items_failed': None}
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_run_diff::reject_summary" -->
### reject_summary · pricing_run_diff
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 5801810
- **Details**: {'open': 5801810, 'total': 6090227, 'terminal': 288417, 'top_reject_reasons': [{'cnt': 5801810, 'reject_reason': 'Could not resolve card_version_id via print_id/external_id/set+collector'}], 'top_term
- **Fix**: Implement Fix 2 and Fix 3 from `docs/MTGSTOCK_REJECT_ANALYSIS.md`, then run `pricing.resolve_price_rejects()`.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_run_diff::observation_volume" -->
### observation_volume · pricing_run_diff
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: {'note': 'fast estimate via pg_class.reltuples; run ANALYZE for precision', 'estimated_rows': 0}
- **Fix**: Run `ANALYZE pricing.price_observation;` after the first successful mtgstock backfill. Also fix the 0% link rate (Fix 2 + Fix 3).
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgjson_run_diff::batch_steps" -->
### batch_steps · mtgjson_run_diff
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: {'per_step': None, 'total_batches': 0, 'total_bytes_mb': None, 'total_items_ok': None, 'total_duration_s': None, 'total_items_failed': None}
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgjson_run_diff::download_resource" -->
### download_resource · mtgjson_run_diff
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: []
- **Fix**: _no fix notes yet_
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="scryfall_integrity::sets-zero-card-versions" -->
### sets-zero-card-versions · scryfall_integrity
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 3
- **Details**: [{'set_id': '974e1012-df4a-44ea-aea4-4bf2f62b4cbf', 'set_code': 'om2', 'set_name': 'Through the Omenpaths 2', 'released_at': '2026-06-26'}, {'set_id': '1226146b-024f-4456-be60-edf06fc054df', 'set_code
- **Fix**: Run the Scryfall daily pipeline; if sets remain empty after a full run, investigate set_code mapping.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="scryfall_integrity::sets-no-icon" -->
### sets-no-icon · scryfall_integrity
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 1031
- **Details**: [{'set_id': '09c785bc-370d-4746-b618-c22d767cb34f', 'set_code': 'p15a', 'set_name': '15th Anniversary Cards'}, {'set_id': 'e9dbe497-c76a-4037-82c1-7ef338d6c54c', 'set_code': 'phtr', 'set_name': '2016
- **Fix**: The Scryfall ETL should populate icon_uri on upsert. Check if the column is included in the upsert SET clause.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="scryfall_integrity::illustration-unreferenced" -->
### illustration-unreferenced · scryfall_integrity
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 1
- **Details**: [{'added_on': '2026-04-25T07:47:43.450471+00:00', 'illustration_id': 'fb2b1ca2-7440-48c2-81c8-84da0a45a626'}]
- **Fix**: Likely a leftover from a partial ETL run. Delete or re-link.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="scryfall_run_diff::run_metrics" -->
### run_metrics · scryfall_run_diff
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: {}
- **Fix**: Check that the scryfall pipeline steps call `ops_repository.record_metric()` and that `track_step` is wiring the run_id correctly.
- **Status**: open
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="scryfall_run_diff::run_resources" -->
### run_resources · scryfall_run_diff
- **Severity**: warn
- **First seen**: 2026-04-30
- **Last seen**: 2026-04-30
- **Row count**: 0
- **Details**: {}
- **Fix**: Ensure the download step upserts a `resource_version` row and links it via `ingestion_run_resources`.
- **Status**: open
<!-- DEBT_ITEM_END -->

---

## Resolved Issues (0)

<!-- DEBT_ITEM_START key="mtgjson_run_diff::staging_residual" -->
### staging_residual · mtgjson_run_diff
- **Severity**: error
- **First seen**: 2026-04-30
- **Resolved**: 2026-04-30
- **Fix applied**: TRUNCATED with mtgjson_integrity::mtgjson-staging-residual
- **Status**: resolved
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="scryfall_integrity::unique-cards-no-version" -->
### unique-cards-no-version · scryfall_integrity
- **Severity**: error
- **First seen**: 2026-04-30
- **Resolved**: 2026-04-30
- **Fix applied**: Deleted: no card_version children, direct DELETE from unique_cards_ref
- **Status**: resolved
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="scryfall_integrity::card-version-no-scryfall-id" -->
### card-version-no-scryfall-id · scryfall_integrity
- **Severity**: error
- **First seen**: 2026-04-30
- **Resolved**: 2026-04-30
- **Fix applied**: Deleted: test artifacts (Test Bulk Card A/B, Delete Test Card 2) — cascaded card_version + unique_cards_ref
- **Status**: resolved
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="card_catalog_report::card_catalog.duplicate_detection.external_id_value_collision" -->
### card_catalog.duplicate_detection.external_id_value_collision · card_catalog_report
- **Severity**: error
- **First seen**: 2026-04-30
- **Resolved**: 2026-04-30
- **Fix applied**: Code fix: excluded tcgplayer_etched_id from uniqueness check — Secret Lair ★ variants share the same TCGPlayer etched ID (upstream behavior). Scoped check now covers only scryfall_id, multiverse_id, mtgjson_id.
- **Status**: resolved
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="pricing_integrity::product-ref-mtg-no-mtg-card-products" -->
### product-ref-mtg-no-mtg-card-products · pricing_integrity
- **Severity**: error
- **First seen**: 2026-04-30
- **Resolved**: 2026-04-30
- **Fix applied**: Deleted: source_product (id 3665011) then product_ref — no price_observation rows referenced it
- **Status**: resolved
<!-- DEBT_ITEM_END -->

<!-- DEBT_ITEM_START key="mtgjson_integrity::mtgjson-staging-residual" -->
### mtgjson-staging-residual · mtgjson_integrity
- **Severity**: error
- **First seen**: 2026-04-30
- **Resolved**: 2026-04-30
- **Fix applied**: TRUNCATED: staging table cleared — no completed pipeline run to attribute data to
- **Status**: resolved
<!-- DEBT_ITEM_END -->

