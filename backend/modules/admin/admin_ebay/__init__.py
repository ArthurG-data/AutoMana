from fastapi import APIRouter
from backend.modules.admin.admin_ebay import routers

admin_ebay_router = APIRouter(
    prefix='/ebay',
    tags=['admin-ebay'],
)

admin_ebay_router.include_router(routers.router)


