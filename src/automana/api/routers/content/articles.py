from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query

from automana.api.dependancies.service_deps import ServiceManagerDep
from automana.api.dependancies.auth.users import CurrentUserDep, get_current_active_user
from automana.api.schemas.StandardisedQueryResponse import ApiResponse
from automana.core.models.content.article import ArticleCreate, ArticleUpdate
from automana.core.exceptions.service_layer_exceptions.content.content_exceptions import (
    ArticleNotFoundError,
    ArticleValidationError,
)

# ── Public router (no auth) ──────────────────────────────────────────────
public_router = APIRouter(prefix="/articles", tags=["Articles"])


@public_router.get("/", summary="List published articles", response_model=ApiResponse,
                   operation_id="articles_list_public")
async def list_articles(
    service_manager: ServiceManagerDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tag: str | None = Query(None),
) -> ApiResponse:
    result = await service_manager.execute_service(
        "content.article.list_public", limit=limit, offset=offset, tag=tag
    )
    return ApiResponse(data=result)


@public_router.get("/{slug}", summary="Get a published article by slug",
                   response_model=ApiResponse, operation_id="articles_get_public")
async def get_article(slug: str, service_manager: ServiceManagerDep) -> ApiResponse:
    try:
        result = await service_manager.execute_service("content.article.get_public", slug=slug)
    except ArticleNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")
    return ApiResponse(data=result)


# ── Admin router (auth-guarded) ──────────────────────────────────────────
admin_router = APIRouter(
    prefix="/articles/admin",
    tags=["Articles (admin)"],
    dependencies=[Depends(get_current_active_user)],
)


@admin_router.get("/", summary="List all articles (draft + published)",
                  response_model=ApiResponse, operation_id="articles_list_admin")
async def list_admin(
    service_manager: ServiceManagerDep, current_user: CurrentUserDep,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
) -> ApiResponse:
    result = await service_manager.execute_service(
        "content.article.list_admin", limit=limit, offset=offset
    )
    return ApiResponse(data=result)


@admin_router.get("/{article_id}", summary="Get any article by id",
                  response_model=ApiResponse, operation_id="articles_get_admin")
async def get_admin(article_id: UUID, service_manager: ServiceManagerDep,
                    current_user: CurrentUserDep) -> ApiResponse:
    try:
        result = await service_manager.execute_service("content.article.get_admin", article_id=article_id)
    except ArticleNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")
    return ApiResponse(data=result)


@admin_router.post("/", summary="Create an article", response_model=ApiResponse,
                   status_code=status.HTTP_201_CREATED, operation_id="articles_create")
async def create(payload: ArticleCreate, service_manager: ServiceManagerDep,
                 current_user: CurrentUserDep) -> ApiResponse:
    result = await service_manager.execute_service(
        "content.article.create", payload=payload, user=current_user
    )
    return ApiResponse(data=result)


@admin_router.patch("/{article_id}", summary="Update an article", response_model=ApiResponse,
                    operation_id="articles_update")
async def update(article_id: UUID, payload: ArticleUpdate, service_manager: ServiceManagerDep,
                 current_user: CurrentUserDep) -> ApiResponse:
    try:
        result = await service_manager.execute_service(
            "content.article.update", article_id=article_id, payload=payload
        )
    except ArticleNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")
    except ArticleValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ApiResponse(data=result)


@admin_router.post("/{article_id}/publish", summary="Publish/unpublish an article",
                   response_model=ApiResponse, operation_id="articles_publish")
async def publish(article_id: UUID, service_manager: ServiceManagerDep,
                  current_user: CurrentUserDep, published: bool = Query(True)) -> ApiResponse:
    try:
        result = await service_manager.execute_service(
            "content.article.publish", article_id=article_id, published=published
        )
    except ArticleNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")
    return ApiResponse(data=result)


@admin_router.delete("/{article_id}", summary="Delete an article", response_model=ApiResponse,
                     operation_id="articles_delete")
async def delete(article_id: UUID, service_manager: ServiceManagerDep,
                 current_user: CurrentUserDep) -> ApiResponse:
    try:
        result = await service_manager.execute_service("content.article.delete", article_id=article_id)
    except ArticleNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")
    return ApiResponse(data=result)
