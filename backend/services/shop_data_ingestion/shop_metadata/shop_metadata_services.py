from backend.services_old.shop_data_ingestion.models import shopify_theme
from backend.services_old.shop_data_ingestion.db import QueryExecutor

 
def insert_theme(values : shopify_theme.InsertTheme , queryExecutor : QueryExecutor.SyncQueryExecutor):
    query = """
    INSERT INTO theme_ref (code, name)
    VALUES (%s, %s)
    ON CONFLICT (code) DO NOTHING;
    """
    queryExecutor.execute_command(query, (values.code, values.name))
   
   
def insert_collection(values : shopify_theme.InsertCollection, queryExecutor : QueryExecutor.SyncQueryExecutor):
    query = """
    INSERT INTO collection_handles (market_id, name)
    VALUES (SELECT market_id FROM market_ref WHERE name = %s), %s
    ON CONFLICT (name) DO NOTHING;
    """
    queryExecutor.execute_command(query,(values.market_id, values.name) )
   
def insert_collection_theme(values : shopify_theme.InsertCollectionTheme, queryExecutor : QueryExecutor.SyncQueryExecutor):
    query = """
    INSERT INTO handles_theme (handle_id, theme_id)
    SELECT
      ch.handle_id,
      tr.theme_id
    FROM
      collection_handles AS ch
      JOIN theme_ref          AS tr ON TRUE
    WHERE
      ch.name = %s
      AND tr.code = %s
    ON CONFLICT (handle_id, theme_id) DO NOTHING;
    """
    queryExecutor.execute_command(query, (values.collection_name, values.theme_code))
   
def get_market_id(name : str)-> int:
    try:
        pass
    except Exception as e:
        print(f"Error fetching market_id for {name}: {e}")
        return -1
