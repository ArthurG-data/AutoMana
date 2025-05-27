
from fastapi import APIRouter,Response
from backend.database.get_database import cursorDep
from backend.shared.dependancies import currentActiveUser
from backend.routers.ebay.services.dev import register_ebay_user
from uuid import UUID

ebay_dev_router = APIRouter(prefix='/dev', tags=['dev'])


@ebay_dev_router .post('/dev/register', description='Add a ebay_user to the database that will be linked to the current user')
async def regist_user(conn: cursorDep, current_user : currentActiveUser, dev_id : UUID):
    register_ebay_user(dev_id, conn, current_user.unique_id)
    return Response(status_code=200, content='Dev added')
