from psycopg2.extensions import connection
from backend.routers.ebay.models.auth import TokenResponse, InputEbaySettings
from psycopg2.extensions import connection
from uuid import UUID
from backend.database.database_utilis import exception_handler
from backend.models.settings import EbaySettings
from backend.routers.ebay.queries import auth, app


def register_app(conn: connection, input:InputEbaySettings, settings : EbaySettings):
    try:
        with conn.cursor() as cursor:
            cursor.execute(app.register_app_query,(input.app_id, input.redirect_uri, input.response_type, input.secret,input.secret, settings.secret_key))
            conn.commit()
    except Exception as e:
        exception_handler(e)


def assign_app(conn : connection, app_id : UUID, ebay_id :str):
    try:
        with conn.cursor() as cursor:
            cursor.execute(app.assign_user_app_query, (ebay_id, app_id,))
            conn.commit()
    except Exception as e:
        exception_handler(e)


def assign_scope(conn: connection, scope : str, app_id : str):
    try:
        with conn.cursor() as cursor:
            cursor.execute(app.assign_scope_query, (app_id,scope,))
            conn.commit()
    except Exception as e:
        exception_handler(e)