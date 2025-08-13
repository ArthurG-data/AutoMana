# backend/dependancies/query_deps.py
from fastapi import Query, Depends
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

class PaginationParams(BaseModel):
    """Pagination parameters"""
    limit: int
    offset: int
    
    @property
    def skip(self) -> int:
        return self.offset

class SortParams(BaseModel):
    """Sorting parameters"""
    sort_by: str
    sort_order: str

class DateRangeParams(BaseModel):
    """Date range filtering"""
    created_after: Optional[datetime]
    created_before: Optional[datetime]

# Dependency functions
async def pagination_params(
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip")
) -> PaginationParams:
    """Standard pagination parameters"""
    return PaginationParams(limit=limit, offset=offset)

async def sort_params(
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order")
) -> SortParams:
    """Standard sorting parameters"""
    return SortParams(sort_by=sort_by, sort_order=sort_order)

async def date_range_params(
    created_after: Optional[datetime] = Query(None, description="Filter items created after this date"),
    created_before: Optional[datetime] = Query(None, description="Filter items created before this date")
) -> DateRangeParams:
    """Date range filtering parameters"""
    return DateRangeParams(created_after=created_after, created_before=created_before)

# User-specific search parameters
async def user_search_params(
    username: Optional[str] = Query(None, description="Search by username"),
    email: Optional[str] = Query(None, description="Search by email (admin only)"),
    full_name: Optional[str] = Query(None, description="Search by full name"),
    search_query: Optional[str] = Query(None, min_length=2, description="General search across username and full name"),
    disabled: Optional[bool] = Query(None, description="Filter by active status"),
    user_id : Optional[UUID] = Query(None, description="Filter by user ID"),
    #role: Optional[str] = Query(None, description="Filter by user role (admin only)")
):
    """User search parameters"""
    return {
        "username": username,
        "email": email,
        "full_name": full_name,
        "search_query": search_query,
        "disabled": disabled,
        "user_id": user_id,
    }

# Card-specific search parameters
async def card_search_params(
    name: Optional[str] = Query(None, description="Filter by card name"),
    set_id: Optional[str] = Query(None, description="Filter by set ID"),
    set_name: Optional[str] = Query(None, description="Filter by set name"),
    card_type: Optional[str] = Query(None, description="Filter by card type"),
    rarity: Optional[str] = Query(None, description="Filter by rarity"),
    mana_cost: Optional[int] = Query(None, ge=0, description="Filter by mana cost")
):
    """Card search parameters"""
    return {
        "name": name,
        "set_id": set_id,
        "set_name": set_name,
        "card_type": card_type,
        "rarity": rarity,
        "mana_cost": mana_cost
    }