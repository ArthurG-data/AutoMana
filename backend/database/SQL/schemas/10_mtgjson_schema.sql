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