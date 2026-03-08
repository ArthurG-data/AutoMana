CREATE TABLE IF NOT EXISTS ops.integrity_checks_card_catalog(
    id SERIAL PRIMARY KEY,
    check_name TEXT NOT NULL UNIQUE,
    check_description TEXT,
    last_run TIMESTAMPTZ,
    bad_records_count INT,
    status TEXT,
    details JSONB,
);
------------------------------count the number of unique cards that do not have an associated card version and log the details of those records 
WITH bad_unique_cards AS (
    SELECT
        ucr.unique_card_id,
        cv.card_version_id
    FROM card_catalog.unique_cards_ref ucr
    LEFT JOIN card_catalog.card_version cv
        ON cv.unique_card_id = ucr.unique_card_id
),
bad AS (
    SELECT unique_card_id
    FROM bad_unique_cards
    WHERE card_version_id IS NULL
),
stats AS (
    SELECT
        COUNT(*)::bigint AS bad_count,
        CASE WHEN COUNT(*) > 0 THEN 'FAIL' ELSE 'PASS' END AS status,
        jsonb_agg(to_jsonb(bad)) AS details
    FROM bad
)
INSERT INTO ops.integrity_checks_card_catalog
    (check_name, check_description, last_run, bad_records_count, status, details)
SELECT
    'Unique Cards without Card Versions',
    'Checks for unique cards that do not have an associated card version.',
    NOW(),
    s.bad_count,
    s.status,
    COALESCE(s.details, '[]'::jsonb)
FROM stats s
ON CONFLICT (check_name)
DO UPDATE SET
    check_description  = EXCLUDED.check_description,
    last_run           = EXCLUDED.last_run,
    bad_records_count  = EXCLUDED.bad_records_count,
    status             = EXCLUDED.status,
    details            = EXCLUDED.details;
------------------------------
--Count the number of card versions that do not have a valid reference to a unique card and log the details of those records
------------------------------
WITH bad_card_versions AS (
    SELECT
        cv.card_version_id,
        cv.unique_card_id
    FROM
        card_catalog.card_version cv
        LEFT JOIN card_catalog.unique_cards_ref ucr ON cv.unique_card_id = ucr.unique_card_id
    WHERE
        ucr.unique_card_id IS NULL
),
stats AS (
    SELECT
        COUNT(*)::bigint AS bad_count,
        CASE WHEN COUNT(*) > 0 THEN 'FAIL' ELSE 'PASS' END AS status,
        jsonb_agg(to_jsonb(bad_card_versions)) AS details
    FROM bad_card_versions
)
INSERT INTO ops.integrity_checks_card_catalog (check_name, check_description, last_run, bad_records_count, status, details)
SELECT
    'Card Versions without Unique Cards',
    'Checks for card versions that do not have a valid reference to a unique card.',
    NOW(),
    s.bad_count,
    s.status,
    COALESCE(s.details, '[]'::jsonb)
FROM stats s
ON CONFLICT (check_name)
DO UPDATE SET
    check_description  = EXCLUDED.check_description,
    last_run           = EXCLUDED.last_run,
    bad_records_count  = EXCLUDED.bad_records_count,
    status             = EXCLUDED.status,
    details            = EXCLUDED.details;
------------------------------
--Check the card faces, each card version should have exactly 2 faces, and each faces shoudl be validated against the unique card reference for that card version, log any records that do not meet this criteria, and the card_version shoulf have the is multiface flag set to true
------------------------------
WITH card_faces_check AS (
    SELECT
        cv.card_version_id,
        cv.unique_card_id,
        COUNT(cf.card_faces_id) AS face_count,
        cv.is_multifaced
    FROM card_catalog.card_version cv
    JOIN card_catalog.unique_cards_ref ucr
        ON cv.unique_card_id = ucr.unique_card_id
    LEFT JOIN card_catalog.card_faces cf
        ON cf.card_version_id = cv.card_version_id
    GROUP BY
        cv.card_version_id,
        cv.unique_card_id,
        cv.is_multifaced
),
bad AS (
    SELECT
        card_version_id,
        unique_card_id,
        face_count,
        is_multifaced
    FROM card_faces_check
    WHERE face_count != 2
       OR is_multifaced != (face_count > 1)
),
stats AS (
    SELECT
        COUNT(*)::bigint AS bad_count,
        CASE WHEN COUNT(*) > 0 THEN 'FAIL' ELSE 'PASS' END AS status,
        jsonb_agg(to_jsonb(bad)) AS details
    FROM bad
)
INSERT INTO ops.integrity_checks_card_catalog
    (check_name, check_description, last_run, bad_records_count, status, details)
SELECT
    'Card Faces Validation',
    'Checks for card versions with incorrect face counts or mismatched is_multifaced flag.',
    NOW(),
    s.bad_count,
    s.status,
    COALESCE(s.details, '[]'::jsonb)
FROM stats s
ON CONFLICT (check_name)
DO UPDATE SET
    check_description = EXCLUDED.check_description,
    last_run          = EXCLUDED.last_run,
    bad_records_count = EXCLUDED.bad_records_count,
    status            = EXCLUDED.status,
    details           = EXCLUDED.details;

-------------------------------
--check that all card_version with faces are label multifaced, and vice versa, log any records that do not meet this criteria, and the card_version should have the is multiface flag set to true
-------------------------------
WITH bad_card_faces AS (
    SELECT
        cv.card_version_id,
        cv.unique_card_id,
        COUNT(cf.card_faces_id) AS face_count,
        cv.is_multifaced
    FROM card_catalog.card_version cv
    LEFT JOIN card_catalog.card_faces cf
        ON cf.card_version_id = cv.card_version_id
    GROUP BY
        cv.card_version_id,
        cv.unique_card_id,
        cv.is_multifaced
),
bad AS (
    SELECT
        card_version_id,
        unique_card_id,
        face_count,
        is_multifaced
    FROM bad_card_faces
    WHERE (face_count > 0 AND is_multifaced = false)
       OR (face_count = 0 AND is_multifaced = true)
),
stats AS (
    SELECT
        COUNT(*)::bigint AS bad_count,
        CASE WHEN COUNT(*) > 0 THEN 'FAIL' ELSE 'PASS' END AS status,
        jsonb_agg(to_jsonb(bad)) AS details
    FROM bad
)
INSERT INTO ops.integrity_checks_card_catalog
    (check_name, check_description, last_run, bad_records_count, status, details)
SELECT
    'Card Faces Multifaced Validation',
    'Checks for card versions with faces not labeled as multifaced or vice versa.',
    NOW(),
    s.bad_count,
    s.status,
    COALESCE(s.details, '[]'::jsonb)
FROM stats s
ON CONFLICT (check_name)
DO UPDATE SET
    check_description = EXCLUDED.check_description,
    last_run          = EXCLUDED.last_run,
    bad_records_count = EXCLUDED.bad_records_count,
    status            = EXCLUDED.status,
    details           = EXCLUDED.details;
-------------------------------
--check for 
-------------------------------

-------------------------------
--check for card version or face not linked to an illustration, log any records that do not meet this criteria, and the card version should have the is illustrated flag set to true
-------------------------------
with bad_card_illustrations as (
    select
        cv.card_version_id,
        cv.unique_card_id,
        cf.card_faces_id,
        ia.illustration_id,
    from card_catalog.card_version cv
    JOIN card_catalog.card_version_illustration cvi
        on cvi.card_version_id = cv.card_version_id
    JOIN card
    left join card_catalog.card_faces cf
        on cf.card_version_id = cv.card_version_id
    left join card_catalog.illustration_agg ia
        on ia.card_version_id = cv.card_version_id or ia.card_faces_id = cf.card_faces_id
),
bad AS (
    SELECT
        card_version_id,
        unique_card_id,
        card_faces_id,
        illustration_id,
        is_illustrated
    FROM bad_card_illustrations
    WHERE illustration_id IS NULL
       OR is_illustrated != (illustration_id IS NOT NULL)
),
stats AS (
    SELECT
        COUNT(*)::bigint AS bad_count,
        CASE WHEN COUNT(*) > 0 THEN 'FAIL' ELSE 'PASS' END AS status,
        jsonb_agg(to_jsonb(bad)) AS details
    FROM bad
)
INSERT INTO ops.integrity_checks_card_catalog
    (check_name, check_description, last_run, bad_records_count, status, details)
SELECT
    'Card Illustrations Validation',
    'Checks for card versions or faces not linked to an illustration or mismatched is_illustrated flag.',
    NOW(),
    s.bad_count,
    s.status,
    COALESCE(s.details, '[]'::jsonb)
FROM stats s
ON CONFLICT (check_name)
DO UPDATE SET
    check_description = EXCLUDED.check_description,
    last_run          = EXCLUDED.last_run,
    bad_records_count = EXCLUDED.bad_records_count,
    status            = EXCLUDED.status,
    details           = EXCLUDED.details;