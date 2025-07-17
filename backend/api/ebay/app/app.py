from fastapi import APIRouter,Response, Depends, Path
from backend.database.get_database import cursorDep
from backend.modules.ebay.models.auth import InputEbaySettings
from backend.modules.ebay.services.app import assign_scope, register_app, assign_app
from uuid import UUID
from backend.services.shop_data_ingestion.db.dependencies import get_sync_query_executor
from backend.services.shop_data_ingestion.db import QueryExecutor

app_router = APIRouter()


@app_router.post('/scopes', description='add a scope to an app')
async def add_user_scope(scope : str, app_id : str = Path(...), queryExecutor:  QueryExecutor = Depends(get_sync_query_executor)):
    assign_scope(queryExecutor,  app_id, scope)

@app_router.post('/', description='add an app to the database')
async def regist_app( input : InputEbaySettings , queryExecutor:  QueryExecutor = Depends(get_sync_query_executor)):
    register_app(queryExecutor, input)


@app_router.post('/{ebay_id}')
async def assign_user_app(queryExecutor:  QueryExecutor = Depends(get_sync_query_executor), app_id : str = Path(...), ebay_id : UUID = Path(...)):
    #add auhoixation later
    assign_app(queryExecutor, app_id, ebay_id)
 


