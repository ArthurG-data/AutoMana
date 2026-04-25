from fastapi import APIRouter
from automana.api.routers.ops.integrity import integrity_router

ops_router = APIRouter(prefix="/ops", tags=["Ops"])
ops_router.include_router(integrity_router)
