from fastapi import APIRouter
from automana.api.routers.content.articles import public_router, admin_router

content_router = APIRouter(prefix="/content")
content_router.include_router(admin_router)   # mount admin BEFORE public so /articles/admin wins over /{slug}
content_router.include_router(public_router)
