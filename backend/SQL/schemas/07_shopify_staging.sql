CREATE UNLOGGED TABLE shopify_staging_raw (
    product_id BIGINT,
    date DATE,
    variation VARCHAR,
    price NUMERIC,
    scraped_at TIMESTAMP
);

CREATE OR REPLACE FUNCTION bulk_insert_shopify_staging(
    p_product_ids BIGINT[],
    p_variant_names VARCHAR[],
    p_prices NUMERIC[],
    p_dates DATE[],
    p_scraped_at TIMESTAMP[]
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    rows_inserted INTEGER := 0;
    i INTEGER;
BEGIN
    -- Validate array lengths
    IF array_length(p_product_ids, 1) != array_length(p_variant_names, 1) OR
       array_length(p_product_ids, 1) != array_length(p_prices, 1) OR
       array_length(p_product_ids, 1) != array_length(p_dates, 1) OR
       array_length(p_product_ids, 1) != array_length(p_scraped_at, 1) THEN
        RAISE EXCEPTION 'All input arrays must have the same length';
    END IF;

    -- Bulk insert using unnest
    INSERT INTO shopify_staging_raw (product_id, variant_name, price, date, scraped_at)
    SELECT 
        unnest(p_product_ids),
        unnest(p_variant_names),
        unnest(p_prices),
        unnest(p_dates),
        unnest(p_scraped_at);
    
    GET DIAGNOSTICS rows_inserted = ROW_COUNT;
    
    RETURN rows_inserted;
END;
$$;