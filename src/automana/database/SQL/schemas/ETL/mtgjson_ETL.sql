CREATE TABLE IF NOT EXISTS prices.mtgjson_card_prices_raw(
    id SERIAL PRIMARY KEY,
    mtgjson_id UUID NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)

