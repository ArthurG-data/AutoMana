insert_market_query =  """
            INSERT INTO market_ref (name, api_url, country_code, city)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (name, city, country_code)
            DO NOTHING;
            """
select_market_id_query = """
            SELECT 
                market_id 
            FROM 
                market_ref 
            WHERE 
                name = $1; 
            """

select_all_markets_query = """
            SELECT market_id, name, api_url, country_code, city, created_at, updated_at FROM market_ref
            """