from psycopg2.extensions import connection
from backend.modules.ebay.models.auth import TokenResponse, InputEbaySettings
from uuid import UUID
from backend.database.database_utilis import exception_handler
from backend.repositories.app_integration.ebay import auth_queries
from backend.schemas.settings import EbaySettings
from backend.repositories.app_integration.ebay import app_queries
from backend.services_old.shop_data_ingestion.db.QueryExecutor import QueryExecutor

def register_app(queryExecutor: QueryExecutor, input:InputEbaySettings, settings : EbaySettings):
    queryExecutor.execute_command(app_queries.register_app_query,(input.app_id, input.redirect_uri, input.response_type, input.secret,input.secret, settings.secret_key))
   
def assign_app(queryExecutor: QueryExecutor, app_id : UUID, ebay_id :str):
    queryExecutor.execute_command(app_queries.assign_user_app_query, (ebay_id, app_id,))
   
def assign_scope(queryExecutor: QueryExecutor, scope : str, app_id : str):
    queryExecutor.execute_command(app_queries.assign_scope_query, (app_id, scope,))
