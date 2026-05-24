insert_market_query = """
    INSERT INTO markets.market_ref (name, api_url, country_code, city)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (name, city, country_code) DO NOTHING;
"""

select_market_id_query = """
    SELECT market_id FROM markets.market_ref WHERE name = $1;
"""

select_all_markets_query = """
    SELECT market_id, name, api_url, country_code, city, source_id, created_at, updated_at
    FROM markets.market_ref;
"""

select_active_pipeline_markets_query = """
    SELECT mr.market_id, mr.name, mr.api_url, mr.country_code, mr.source_id
    FROM markets.market_ref mr
    WHERE mr.api_url IS NOT NULL
      AND mr.source_id IS NOT NULL;
"""
