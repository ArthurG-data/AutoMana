from psycopg2.extensions import connection
from uuid import UUID
from backend.database.database_utilis import exception_handler
from backend.routers.ebay.queries import dev


def register_ebay_user(dev_id : UUID , conn : connection, user_id : UUID):

    try:
        with conn.cursor() as cursor:
            cursor.execute(dev.register_user_query,(user_id, dev_id,))
            conn.commit()
    except Exception as e:
        exception_handler(e)
