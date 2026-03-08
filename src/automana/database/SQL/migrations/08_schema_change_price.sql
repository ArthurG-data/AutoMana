-- ============================================================================
-- PHASE 1: Add the finish_type column in proce_observation
-- ============================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS pricing.price_type (
    type_id SERIAL PRIMARY KEY,
    type_name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO pricing.price_type (type_name) VALUES 
('retail'), 
('buylist')
ON CONFLICT (type_name) DO NOTHING;
ALTER TABLE pricing.price_observation
ADD COLUMN IF NOT EXISTS finish_id INT DEFAULT 1
REFERENCES pricing.card_finished(finish_id);
ALTER TABLE pricing.price_observation
ADD COLUMN IF NOT EXISTS price_type_id INT REFERENCES pricing.price_type(type_id) DEFAULT 1;

-- ============================================================================
-- PHASE 2: migrate foil status from price_metric -> price_observation
-- ============================================================================

-- migrate old metric ids to new structure
UPDATE pricing.price_observation
SET metric_id = 6, finish_id = 2
WHERE metric_id = 8;

UPDATE pricing.price_observation
SET metric_id = 7, finish_id = 2
WHERE metric_id = 13;

-- remove deprecated metrics
DELETE FROM pricing.price_metric
WHERE metric_id IN (8, 13);

-- ensure all existing records have a finish type (default nonfoil)
UPDATE pricing.price_observation
SET finish_id = 1
WHERE finish_id IS NULL;


DO $$
DECLARE
    v_bad_metrics INT;
    v_null_finish INT;
BEGIN
    -- Check no deprecated metric ids remain
    SELECT COUNT(*) INTO v_bad_metrics
    FROM pricing.price_observation
    WHERE metric_id IN (8, 13);

    IF v_bad_metrics > 0 THEN
        RAISE EXCEPTION
            'Migration validation failed: % rows still reference deprecated metric_id (8 or 13)',
            v_bad_metrics;
    END IF;

    -- Check all rows have a finish_id
    SELECT COUNT(*) INTO v_null_finish
    FROM pricing.price_observation
    WHERE finish_id IS NULL;

    IF v_null_finish > 0 THEN
        RAISE EXCEPTION
            'Migration validation failed: % rows still have NULL finish_id',
            v_null_finish;
    END IF;

    RAISE NOTICE 'Migration validation passed: no deprecated metrics and all rows have finish_id.';
END $$;

COMMIT;

-- ============================================================================
-- PHASE 3: Add the card_version_id in the price_observation table and populate it based on the card_id and finish_id
-- ============================================================================
ALTER TABLE pricing.price_observation
ADD COLUMN IF NOT EXISTS card_version_id UUID REFERENCES card_catalog.card_version(card_version_id);
--
