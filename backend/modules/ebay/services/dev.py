from fastapi import Depends
from uuid import UUID
from backend.database.database_utilis import exception_handler
from backend.modules.ebay.queries import dev
from backend.services.shop_data_ingestion.db import QueryExecutor
from backend.services.shop_data_ingestion.db.dependencies import get_sync_query_executor


def register_ebay_user(dev_id : UUID , user_id : UUID, queryExecutor : QueryExecutor.SyncQueryExecutor):
    queryExecutor.execute_command(dev.register_user_query,(user_id, dev_id,))
   