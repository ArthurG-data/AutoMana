
from fastapi import APIRouter,Response, Depends
from backend.database.get_database import cursorDep
from backend.modules.auth.dependancies import currentActiveUser
from backend.modules.ebay.services.dev import register_ebay_user
from uuid import UUID
from backend.services_old.shop_data_ingestion.db import QueryExecutor
from backend.services_old.shop_data_ingestion.db.dependencies import get_sync_query_executor

ebay_dev_router = APIRouter(prefix='/dev', tags=['dev'])

@ebay_dev_router .post('/register', description='Add a ebay_user to the database that will be linked to the current user')
async def regist_user(current_user : currentActiveUser, dev_id : UUID, queryExecutor : QueryExecutor.SyncQueryExecutor = Depends(get_sync_query_executor)):
    register_ebay_user(dev_id, current_user.unique_id, queryExecutor)
    
