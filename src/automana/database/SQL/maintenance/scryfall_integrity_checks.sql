-- =============================================================================
-- scryfall_integrity_checks.sql
--
-- Purpose  : Periodic loose-data / orphan checks for the Scryfall pipeline's
--            card_catalog domain. Re-implements the three checks found in
--            card_catalog.integrity_checks_card_catalog as read-only SELECTs
--            (this file is entirely idempotent — no writes), then adds every
--            additional pattern flagged in the schema briefing.
--
-- How to run:
--   psql -U <role> -d automana -f scryfall_integrity_checks.sql
--
-- Expected frequency : Daily (run after scryfall_daily completes) and on-demand.
--
-- Interpretation of severity:
--   'error' — FK-orphan-shaped or constraint-violation-shaped finding;
--             these SHOULD be 0 in a healthy database.
--   'warn'  — soft-data anomaly or threshold exceeded; investigate but may
--             be benign depending on context.
--   'info'  — known-benign non-zero count (e.g. cards with no legalities is
--             valid for tokens/emblems); review but do not page.
--
-- Output shape (every block):
--   check_name TEXT, severity TEXT, row_count BIGINT, details JSONB
--
-- Key schema facts baked into this file:
--   - Sentinel UUIDs excluded from orphan checks:
--       '00000000-0000-0000-0000-000000000001'  Unknown Artist
--       '00000000-0000-0000-0000-000000000002'  MISSING_SET
--   - card_catalog.sets.updated_at is DATE (not TIMESTAMPTZ).
--   - card_version uses ON CONFLICT DO NOTHING — updated_at = insert time only.
--   - face_illustration.face_id references card_faces.card_faces_id (double-plural PK).
--   - card_external_identifier UNIQUE (card_identifier_ref_id, value) — duplicate
--     scryfall_id across card_versions would be rejected at write time.
--   - pricing.print_price_daily/weekly FK to card_catalog.card_version has no
--     ON DELETE clause — orphan rows there are real drift.
--   - color_produced is declared but never written by the pipeline — any rows
--     indicate an out-of-band writer.
-- =============================================================================

WITH

-- ---------------------------------------------------------------------------
-- CHECK 01: unique_cards_ref rows with no card_version (re-implements
--           "Unique Cards without Card Versions" from integrity_checks_card_catalog).
--           Non-zero = orphan unique card records with no printings — error.
-- ---------------------------------------------------------------------------
chk_01_unique_cards_no_version AS (
    SELECT
        'unique-cards-no-version'::TEXT                   AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT ucr.unique_card_id, ucr.card_name
                FROM card_catalog.unique_cards_ref ucr
                LEFT JOIN card_catalog.card_version cv ON cv.unique_card_id = ucr.unique_card_id
                WHERE cv.card_version_id IS NULL
                ORDER BY ucr.card_name
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.unique_cards_ref ucr
    LEFT JOIN card_catalog.card_version cv ON cv.unique_card_id = ucr.unique_card_id
    WHERE cv.card_version_id IS NULL
),

-- ---------------------------------------------------------------------------
-- CHECK 02: card_version rows with no matching unique_cards_ref (re-implements
--           "Card Versions without Unique Cards" from integrity_checks_card_catalog).
--           Non-zero = broken FK — should be prevented by DB constraint; error.
-- ---------------------------------------------------------------------------
chk_02_card_version_no_unique_card AS (
    SELECT
        'card-version-no-unique-card'::TEXT               AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT cv.card_version_id, cv.unique_card_id
                FROM card_catalog.card_version cv
                LEFT JOIN card_catalog.unique_cards_ref ucr ON ucr.unique_card_id = cv.unique_card_id
                WHERE ucr.unique_card_id IS NULL
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.card_version cv
    LEFT JOIN card_catalog.unique_cards_ref ucr ON ucr.unique_card_id = cv.unique_card_id
    WHERE ucr.unique_card_id IS NULL
),

-- ---------------------------------------------------------------------------
-- CHECK 03: is_multifaced flag vs actual face count mismatch (re-implements
--           "Card Faces Multifaced Validation" from integrity_checks_card_catalog).
--           is_multifaced=true but 0 faces, or is_multifaced=false but faces exist.
--           Non-zero = import logic fault; error.
-- ---------------------------------------------------------------------------
chk_03_multifaced_flag_mismatch AS (
    SELECT
        'multifaced-flag-mismatch'::TEXT                  AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT x.card_version_id, x.is_multifaced, x.face_count
                FROM (
                    SELECT
                        cv.card_version_id,
                        cv.is_multifaced,
                        COUNT(cf.card_faces_id)::int AS face_count
                    FROM card_catalog.card_version cv
                    LEFT JOIN card_catalog.card_faces cf ON cf.card_version_id = cv.card_version_id
                    GROUP BY cv.card_version_id, cv.is_multifaced
                ) x
                WHERE (x.face_count > 0 AND x.is_multifaced = false)
                   OR (x.face_count = 0 AND x.is_multifaced = true)
                LIMIT 5
            ) s
        ) AS details
    FROM (
        SELECT
            cv.card_version_id,
            cv.is_multifaced,
            COUNT(cf.card_faces_id) AS face_count
        FROM card_catalog.card_version cv
        LEFT JOIN card_catalog.card_faces cf ON cf.card_version_id = cv.card_version_id
        GROUP BY cv.card_version_id, cv.is_multifaced
    ) agg
    WHERE (agg.face_count > 0 AND agg.is_multifaced = false)
       OR (agg.face_count = 0 AND agg.is_multifaced = true)
),

-- ---------------------------------------------------------------------------
-- CHECK 04: sets with zero card_versions.
--           Expected for newly ingested sets before cards load; warn not error.
-- ---------------------------------------------------------------------------
chk_04_sets_zero_card_versions AS (
    SELECT
        'sets-zero-card-versions'::TEXT                   AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT s2.set_id, s2.set_code, s2.set_name, s2.released_at
                FROM card_catalog.sets s2
                WHERE s2.set_id != '00000000-0000-0000-0000-000000000002'
                AND NOT EXISTS (
                    SELECT 1 FROM card_catalog.card_version cv
                    WHERE cv.set_id = s2.set_id
                )
                ORDER BY s2.released_at DESC
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.sets s
    WHERE s.set_id != '00000000-0000-0000-0000-000000000002'
      AND NOT EXISTS (
          SELECT 1 FROM card_catalog.card_version cv WHERE cv.set_id = s.set_id
      )
),

-- ---------------------------------------------------------------------------
-- CHECK 05: sets with no icon_set row.
--           Each set ingested by the pipeline should get an icon link.
--           Non-zero = partial ingest or icon URI missing from payload; warn.
-- ---------------------------------------------------------------------------
chk_05_sets_no_icon AS (
    SELECT
        'sets-no-icon'::TEXT                              AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT s2.set_id, s2.set_code, s2.set_name
                FROM card_catalog.sets s2
                WHERE s2.set_id != '00000000-0000-0000-0000-000000000002'
                  AND NOT EXISTS (
                      SELECT 1 FROM card_catalog.icon_set ic WHERE ic.set_id = s2.set_id
                  )
                ORDER BY s2.set_name
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.sets s
    WHERE s.set_id != '00000000-0000-0000-0000-000000000002'
      AND NOT EXISTS (
          SELECT 1 FROM card_catalog.icon_set ic WHERE ic.set_id = s.set_id
      )
),

-- ---------------------------------------------------------------------------
-- CHECK 06: sets.parent_set points to a non-existent set_id.
--           Should not happen if parent sets are inserted before children; error.
-- ---------------------------------------------------------------------------
chk_06_parent_set_missing AS (
    SELECT
        'parent-set-missing'::TEXT                        AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT s2.set_id, s2.set_code, s2.set_name, s2.parent_set
                FROM card_catalog.sets s2
                WHERE s2.parent_set IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM card_catalog.sets p WHERE p.set_id = s2.parent_set
                  )
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.sets s
    WHERE s.parent_set IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM card_catalog.sets p WHERE p.set_id = s.parent_set
      )
),

-- ---------------------------------------------------------------------------
-- CHECK 07: artists_ref rows (excluding Unknown Artist sentinel) with no
--           illustration_artist row. Every real artist should link to at
--           least one illustration; warn — could be data-scrubbed reprints.
-- ---------------------------------------------------------------------------
chk_07_artist_no_illustration AS (
    SELECT
        'artist-no-illustration'::TEXT                    AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT ar.artist_id, ar.artist_name
                FROM card_catalog.artists_ref ar
                WHERE ar.artist_id != '00000000-0000-0000-0000-000000000001'
                  AND NOT EXISTS (
                      SELECT 1 FROM card_catalog.illustration_artist ia
                      WHERE ia.artist_id = ar.artist_id
                  )
                ORDER BY ar.artist_name
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.artists_ref ar
    WHERE ar.artist_id != '00000000-0000-0000-0000-000000000001'
      AND NOT EXISTS (
          SELECT 1 FROM card_catalog.illustration_artist ia WHERE ia.artist_id = ar.artist_id
      )
),

-- ---------------------------------------------------------------------------
-- CHECK 08: illustrations with no illustration_artist row.
--           Every illustration should credit an artist; error.
-- ---------------------------------------------------------------------------
chk_08_illustration_no_artist AS (
    SELECT
        'illustration-no-artist'::TEXT                    AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT i.illustration_id, i.added_on
                FROM card_catalog.illustrations i
                WHERE NOT EXISTS (
                    SELECT 1 FROM card_catalog.illustration_artist ia
                    WHERE ia.illustration_id = i.illustration_id
                )
                ORDER BY i.added_on DESC
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.illustrations i
    WHERE NOT EXISTS (
        SELECT 1 FROM card_catalog.illustration_artist ia
        WHERE ia.illustration_id = i.illustration_id
    )
),

-- ---------------------------------------------------------------------------
-- CHECK 09: illustrations not referenced by card_version_illustration AND
--           not referenced by face_illustration — completely dangling records.
--           Non-zero = pipeline left orphan blobs; warn.
-- ---------------------------------------------------------------------------
chk_09_illustration_unreferenced AS (
    SELECT
        'illustration-unreferenced'::TEXT                 AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT i.illustration_id, i.added_on
                FROM card_catalog.illustrations i
                WHERE NOT EXISTS (
                    SELECT 1 FROM card_catalog.card_version_illustration cvi
                    WHERE cvi.illustration_id = i.illustration_id
                )
                AND NOT EXISTS (
                    SELECT 1 FROM card_catalog.face_illustration fi
                    WHERE fi.illustration_id = i.illustration_id
                )
                ORDER BY i.added_on DESC
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.illustrations i
    WHERE NOT EXISTS (
        SELECT 1 FROM card_catalog.card_version_illustration cvi
        WHERE cvi.illustration_id = i.illustration_id
    )
    AND NOT EXISTS (
        SELECT 1 FROM card_catalog.face_illustration fi
        WHERE fi.illustration_id = i.illustration_id
    )
),

-- ---------------------------------------------------------------------------
-- CHECK 10: card_faces rows where the parent card_version.is_multifaced = false.
--           Faces should only exist for multifaced cards; error.
-- ---------------------------------------------------------------------------
chk_10_face_on_non_multifaced AS (
    SELECT
        'face-on-non-multifaced-card'::TEXT               AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT cf.card_faces_id, cf.card_version_id, cf.name AS face_name, cv.is_multifaced
                FROM card_catalog.card_faces cf
                JOIN card_catalog.card_version cv ON cf.card_version_id = cv.card_version_id
                WHERE cv.is_multifaced = false
                ORDER BY cf.card_version_id
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.card_faces cf
    JOIN card_catalog.card_version cv ON cf.card_version_id = cv.card_version_id
    WHERE cv.is_multifaced = false
),

-- ---------------------------------------------------------------------------
-- CHECK 11: face_illustration.face_id with no matching card_faces row.
--           face_illustration.face_id references card_faces.card_faces_id
--           (note the double-plural PK column name). Error.
-- ---------------------------------------------------------------------------
chk_11_face_illustration_orphan_face AS (
    SELECT
        'face-illustration-orphan-face'::TEXT             AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT fi.face_id, fi.illustration_id
                FROM card_catalog.face_illustration fi
                WHERE NOT EXISTS (
                    SELECT 1 FROM card_catalog.card_faces cf
                    WHERE cf.card_faces_id = fi.face_id
                )
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.face_illustration fi
    WHERE NOT EXISTS (
        SELECT 1 FROM card_catalog.card_faces cf WHERE cf.card_faces_id = fi.face_id
    )
),

-- ---------------------------------------------------------------------------
-- CHECK 12: card_version with is_multifaced=true but zero card_faces rows.
--           Indicates the faces block was skipped or failed to write; error.
-- ---------------------------------------------------------------------------
chk_12_multifaced_no_faces AS (
    SELECT
        'multifaced-card-no-faces'::TEXT                  AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT cv.card_version_id, cv.unique_card_id, cv.set_id
                FROM card_catalog.card_version cv
                WHERE cv.is_multifaced = true
                  AND NOT EXISTS (
                      SELECT 1 FROM card_catalog.card_faces cf
                      WHERE cf.card_version_id = cv.card_version_id
                  )
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.card_version cv
    WHERE cv.is_multifaced = true
      AND NOT EXISTS (
          SELECT 1 FROM card_catalog.card_faces cf WHERE cf.card_version_id = cv.card_version_id
      )
),

-- ---------------------------------------------------------------------------
-- CHECK 13: card_external_identifier rows with NULL value.
--           The column is NOT NULL in DDL — this should never occur but
--           guards against future schema relaxation; error.
-- ---------------------------------------------------------------------------
chk_13_external_id_null_value AS (
    SELECT
        'external-id-null-value'::TEXT                    AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT cei.card_version_id, cei.card_identifier_ref_id
                FROM card_catalog.card_external_identifier cei
                WHERE cei.value IS NULL
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.card_external_identifier cei
    WHERE cei.value IS NULL
),

-- ---------------------------------------------------------------------------
-- CHECK 14: card_version with no scryfall_id external identifier.
--           Every Scryfall-ingested card should have a scryfall_id record.
--           Non-zero = insert_full_card_version failed to write the identifier; error.
--           Note: UNIQUE (card_identifier_ref_id, value) means duplicate scryfall_ids
--           across card_versions would have been rejected at write time.
-- ---------------------------------------------------------------------------
chk_14_card_version_no_scryfall_id AS (
    SELECT
        'card-version-no-scryfall-id'::TEXT               AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT cv.card_version_id, cv.set_id, cv.collector_number
                FROM card_catalog.card_version cv
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM card_catalog.card_external_identifier cei
                    JOIN card_catalog.card_identifier_ref cir
                        ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
                    WHERE cir.identifier_name = 'scryfall_id'
                      AND cei.card_version_id = cv.card_version_id
                )
                ORDER BY cv.created_at DESC
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.card_version cv
    WHERE NOT EXISTS (
        SELECT 1
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
            ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
        WHERE cir.identifier_name = 'scryfall_id'
          AND cei.card_version_id = cv.card_version_id
    )
),

-- ---------------------------------------------------------------------------
-- CHECK 15: unique_cards_ref with no legalities rows.
--           Tokens, emblems, and some specialty cards legitimately have none.
--           Severity=info — large counts (> 5 % of total) may warrant review.
-- ---------------------------------------------------------------------------
chk_15_unique_card_no_legalities AS (
    SELECT
        'unique-card-no-legalities'::TEXT                 AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT ucr.unique_card_id, ucr.card_name
                FROM card_catalog.unique_cards_ref ucr
                WHERE NOT EXISTS (
                    SELECT 1 FROM card_catalog.legalities l
                    WHERE l.unique_card_id = ucr.unique_card_id
                )
                ORDER BY ucr.card_name
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.unique_cards_ref ucr
    WHERE NOT EXISTS (
        SELECT 1 FROM card_catalog.legalities l WHERE l.unique_card_id = ucr.unique_card_id
    )
),

-- ---------------------------------------------------------------------------
-- CHECK 16: pricing.print_price_daily referencing missing card_version_id.
--           The FK has no ON DELETE clause — orphan rows mean real drift
--           (card_version was deleted or never existed); error.
-- ---------------------------------------------------------------------------
chk_16_ppd_orphan_card_version AS (
    SELECT
        'print-price-daily-orphan-card-version'::TEXT     AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT ppd.card_version_id, ppd.price_date
                FROM pricing.print_price_daily ppd
                WHERE NOT EXISTS (
                    SELECT 1 FROM card_catalog.card_version cv
                    WHERE cv.card_version_id = ppd.card_version_id
                )
                ORDER BY ppd.price_date DESC
                LIMIT 5
            ) s
        ) AS details
    FROM pricing.print_price_daily ppd
    WHERE NOT EXISTS (
        SELECT 1 FROM card_catalog.card_version cv
        WHERE cv.card_version_id = ppd.card_version_id
    )
),

-- ---------------------------------------------------------------------------
-- CHECK 17: pricing.print_price_weekly referencing missing card_version_id.
--           Same drift concern as CHECK 16; error.
-- ---------------------------------------------------------------------------
chk_17_ppw_orphan_card_version AS (
    SELECT
        'print-price-weekly-orphan-card-version'::TEXT    AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT ppw.card_version_id, ppw.price_week
                FROM pricing.print_price_weekly ppw
                WHERE NOT EXISTS (
                    SELECT 1 FROM card_catalog.card_version cv
                    WHERE cv.card_version_id = ppw.card_version_id
                )
                ORDER BY ppw.price_week DESC
                LIMIT 5
            ) s
        ) AS details
    FROM pricing.print_price_weekly ppw
    WHERE NOT EXISTS (
        SELECT 1 FROM card_catalog.card_version cv
        WHERE cv.card_version_id = ppw.card_version_id
    )
),

-- ---------------------------------------------------------------------------
-- CHECK 18: card_version rows routed to MISSING_SET sentinel.
--           Non-zero = insert_full_card_version could not resolve the set_name.
--           Expected to be 0 after a full set import; warn for any non-zero.
-- ---------------------------------------------------------------------------
chk_18_card_version_missing_set AS (
    SELECT
        'card-version-routed-to-missing-set'::TEXT        AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT cv.card_version_id, cv.unique_card_id, cv.collector_number, cv.created_at
                FROM card_catalog.card_version cv
                WHERE cv.set_id = '00000000-0000-0000-0000-000000000002'
                ORDER BY cv.created_at DESC
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.card_version cv
    WHERE cv.set_id = '00000000-0000-0000-0000-000000000002'
),

-- ---------------------------------------------------------------------------
-- CHECK 19: card_catalog.color_produced non-empty.
--           This table is declared but never written by the pipeline.
--           Any row means an out-of-band writer exists; warn.
-- ---------------------------------------------------------------------------
chk_19_color_produced_non_empty AS (
    SELECT
        'color-produced-non-empty'::TEXT                  AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT cp.unique_card_id, cp.color_id, cp.created_at
                FROM card_catalog.color_produced cp
                ORDER BY cp.created_at DESC
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.color_produced cp
),

-- ---------------------------------------------------------------------------
-- CHECK 20: card_version with NULL set_id.
--           set_id is NOT NULL in the DDL — should be impossible; error.
-- ---------------------------------------------------------------------------
chk_20_card_version_null_set_id AS (
    SELECT
        'card-version-null-set-id'::TEXT                  AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT cv.card_version_id, cv.unique_card_id
                FROM card_catalog.card_version cv
                WHERE cv.set_id IS NULL
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.card_version cv
    WHERE cv.set_id IS NULL
),

-- ---------------------------------------------------------------------------
-- CHECK 21: illustrations with NULL image_uris while referenced by
--           card_version_illustration.
--           Single-faced cards must have image_uris; warn (may be mid-import).
-- ---------------------------------------------------------------------------
chk_21_illustration_null_image_uris AS (
    SELECT
        'illustration-null-image-uris'::TEXT              AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT i.illustration_id, cvi.card_version_id
                FROM card_catalog.illustrations i
                JOIN card_catalog.card_version_illustration cvi
                    ON cvi.illustration_id = i.illustration_id
                WHERE i.image_uris IS NULL
                ORDER BY i.added_on DESC
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.illustrations i
    JOIN card_catalog.card_version_illustration cvi ON cvi.illustration_id = i.illustration_id
    WHERE i.image_uris IS NULL
),

-- ---------------------------------------------------------------------------
-- CHECK 22: scryfall_migration merge records (strategy='merge') where the
--           new_scryfall_id is not present as a scryfall_id external identifier.
--           Indicates the target of a merge has not been ingested; warn.
-- ---------------------------------------------------------------------------
chk_22_migration_merge_missing_target AS (
    SELECT
        'migration-merge-missing-target'::TEXT            AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT sm.id AS migration_id, sm.old_scryfall_id, sm.new_scryfall_id, sm.performed_at
                FROM card_catalog.scryfall_migration sm
                WHERE sm.migration_strategy = 'merge'
                  AND sm.new_scryfall_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM card_catalog.card_external_identifier cei
                      JOIN card_catalog.card_identifier_ref cir
                          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
                      WHERE cir.identifier_name = 'scryfall_id'
                        AND cei.value = sm.new_scryfall_id::text
                  )
                ORDER BY sm.performed_at DESC
                LIMIT 5
            ) s
        ) AS details
    FROM card_catalog.scryfall_migration sm
    WHERE sm.migration_strategy = 'merge'
      AND sm.new_scryfall_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM card_catalog.card_external_identifier cei
          JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
          WHERE cir.identifier_name = 'scryfall_id'
            AND cei.value = sm.new_scryfall_id::text
      )
),

-- ---------------------------------------------------------------------------
-- CHECK 23: ops runs for scryfall_daily stuck in 'running' for more than 2h.
--           Should be 0 in normal operation; error.
-- ---------------------------------------------------------------------------
chk_23_stuck_runs AS (
    SELECT
        'scryfall-runs-stuck-running'::TEXT               AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT ir.id, ir.run_key, ir.started_at, ir.current_step,
                       EXTRACT(EPOCH FROM now() - ir.started_at) / 3600 AS hours_running
                FROM ops.ingestion_runs ir
                WHERE ir.pipeline_name = 'scryfall_daily'
                  AND ir.status = 'running'
                  AND ir.started_at < now() - INTERVAL '2 hours'
                ORDER BY ir.started_at
                LIMIT 5
            ) s
        ) AS details
    FROM ops.ingestion_runs ir
    WHERE ir.pipeline_name = 'scryfall_daily'
      AND ir.status = 'running'
      AND ir.started_at < now() - INTERVAL '2 hours'
),

-- ---------------------------------------------------------------------------
-- CHECK 24: ops.ingestion_run_steps for the last scryfall_daily run where
--           status != 'success'. Surfaces failed or still-running steps.
-- ---------------------------------------------------------------------------
last_run_for_checks AS (
    SELECT id AS run_id
    FROM ops.ingestion_runs
    WHERE pipeline_name = 'scryfall_daily'
    ORDER BY started_at DESC
    LIMIT 1
),
chk_24_last_run_failed_steps AS (
    SELECT
        'last-run-failed-steps'::TEXT                     AS check_name,
        COUNT(*)::BIGINT                                  AS bad_count,
        (
            SELECT jsonb_agg(to_jsonb(s))
            FROM (
                SELECT irs.step_name, irs.status, irs.error_code, irs.error_details, irs.started_at, irs.ended_at
                FROM ops.ingestion_run_steps irs
                JOIN last_run_for_checks lr ON irs.ingestion_run_id = lr.run_id
                WHERE irs.status != 'success'
                ORDER BY irs.started_at
                LIMIT 5
            ) s
        ) AS details
    FROM ops.ingestion_run_steps irs
    JOIN last_run_for_checks lr ON irs.ingestion_run_id = lr.run_id
    WHERE irs.status != 'success'
)

-- ---------------------------------------------------------------------------
-- Final UNION — fold all checks into the standard shape.
-- ---------------------------------------------------------------------------
SELECT
    check_name,
    CASE
        WHEN check_name IN (
            'unique-cards-no-version',
            'card-version-no-unique-card',
            'multifaced-flag-mismatch',
            'parent-set-missing',
            'illustration-no-artist',
            'face-on-non-multifaced-card',
            'face-illustration-orphan-face',
            'multifaced-card-no-faces',
            'external-id-null-value',
            'card-version-no-scryfall-id',
            'print-price-daily-orphan-card-version',
            'print-price-weekly-orphan-card-version',
            'card-version-null-set-id',
            'scryfall-runs-stuck-running',
            'last-run-failed-steps'
        ) THEN CASE WHEN bad_count > 0 THEN 'error' ELSE 'info' END
        WHEN check_name IN (
            'unique-card-no-legalities'
        ) THEN 'info'  -- benign for tokens/emblems regardless of count
        ELSE           CASE WHEN bad_count > 0 THEN 'warn'  ELSE 'info' END
    END                                                   AS severity,
    bad_count                                             AS row_count,
    COALESCE(details, '[]'::jsonb)                        AS details
FROM (
    SELECT check_name, bad_count, details FROM chk_01_unique_cards_no_version
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_02_card_version_no_unique_card
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_03_multifaced_flag_mismatch
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_04_sets_zero_card_versions
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_05_sets_no_icon
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_06_parent_set_missing
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_07_artist_no_illustration
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_08_illustration_no_artist
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_09_illustration_unreferenced
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_10_face_on_non_multifaced
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_11_face_illustration_orphan_face
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_12_multifaced_no_faces
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_13_external_id_null_value
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_14_card_version_no_scryfall_id
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_15_unique_card_no_legalities
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_16_ppd_orphan_card_version
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_17_ppw_orphan_card_version
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_18_card_version_missing_set
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_19_color_produced_non_empty
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_20_card_version_null_set_id
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_21_illustration_null_image_uris
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_22_migration_merge_missing_target
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_23_stuck_runs
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_24_last_run_failed_steps
) all_checks
;
-- No ORDER BY — the Python service layer partitions rows by severity
-- into errors/warnings/passed arrays, and PG's outer-SELECT alias
-- resolution rules don't let `ORDER BY CASE severity WHEN ...` see the
-- alias here (the alias only exists on the result columns, not in the
-- underlying `all_checks` subquery's scope).
