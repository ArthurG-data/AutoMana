CREATE TABLE IF NOT EXISTS pricing.mtgjson_staging (
  cardFinish TEXT,
  currency TEXT,
  date DATE,
  gameAvailability TEXT,
  price FLOAT,
  priceProvider TEXT,
  providerListing TEXT,
  uuid TEXT,
    -- Audit
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pricing.mtgjson_payloads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  filename TEXT,
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing.mtgjson_card_prices_staging (
    id SERIAL PRIMARY KEY,
    card_uuid TEXT NOT NULL,
    price_source TEXT NOT NULL, --the provenance
    price_type  TEXT, --buylist or retail
    finish_type TEXT NOT NULL, --finish or foil or etched or showcase
    currency TEXT NOT NULL,
    price_value FLOAT NOT NULL,
    price_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE PROCEDURE pricing.process_mtgjson_payload(payload_id UUID)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Fetch the payload record
    IF NOT EXISTS (SELECT 1 FROM pricing.mtgjson_payloads WHERE id = payload_id) THEN
        RAISE EXCEPTION 'Payload with ID % not found', payload_id;
    END IF;

    INSERT INTO pricing.mtgjson_card_prices_staging (card_uuid, price_source, price_type,finish_type, price_date, price_value, currency)
    SELECT 
      card_key AS card_uuid,
      source_key as source_key,
      price_type_key as price_type_key,
      finish_type_key as finish_type_key,
      price_date::DATE AS price_date,
      price_value::NUMERIC AS price_value,
      (source_val->>'currency') AS currency
    FROM pricing.mtgjson_payloads,
    LATERAL jsonb_each(payload -> 'data') AS data_entry(card_key, card_val),
    LATERAL jsonb_each(card_val -> 'paper') AS source_entry(source_key, source_val),
    LATERAL jsonb_each(source_val) AS price_type_entry(price_type_key, price_type_val),
    LATERAL jsonb_each(price_type_val) AS finish_entry(finish_type_key, finish_type_val),
    LATERAL jsonb_each(finish_type_val) AS date_entry(price_date, price_value)
    WHERE id = payload_id
      AND price_type_key NOT IN ('currency');
END;
$$;

----------------------------------------------------------------next, find reference to data in the table, for source for example
#need to grab the price metric and price source id from the JSON and insert into the staging table, then we can transform and insert into the final table
CREATE OR REPLACE PROCEDURE pricing.stage_mtgjson_prices()
LANGUAGE plpgsql
AS $$
DECLARE
    v_source_id INT;
    v_source_names TEXT[];
    V_finish_names TEXT[];
    v_finish_id INT;
    v_price_metric INT;
    v_card_uuid UUID;
BEGIN
  SELECT DISTINCT price_source 
  INTO v_source_id
  FROM pricing.mtgjson_card_prices_staging;

  --replace the type normal by NONFOIL
  UPDATE pricing.mtgjson_card_prices_staging
  SET finish_type = 'NONFOIL'
  WHERE finish_type = 'normal';

  SELECT DISTINCT finish_type 
  INTO v_finish_names
  FROM pricing.mtgjson_card_prices_staging;
  -- add the sources if not existing in the db already
  DO LOOP
    FOR EACH source_name IN v_source_names;
        IF EXISTS (SELECT 1 FROM pricing.source WHERE name = source_name) THEN
            SELECT id INTO v_source_id FROM pricing.source WHERE name = source_name;
        ELSE
            INSERT INTO pricing.source (name) VALUES (source_name) RETURNING id INTO v_source_id;
        END IF;
  END LOOP;
  --find the finish
  DO LOOP;
    FOR EACH finish_name IN V_finish_names;
        IF EXISTS (SELECT 1 FROM pricing.card_finished WHERE code = finish_name) THEN
            SELECT id INTO v_finish_id FROM pricing.card_finished WHERE code = finish_name;
        ELSE
            INSERT INTO pricing.card_finished (code) VALUES (finish_name) RETURNING id INTO v_finish_id;
        END IF; 
  END LOOP;
  --find the mertric
  




END;
$$;