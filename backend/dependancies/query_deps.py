# backend/dependancies/query_deps.py
from fastapi import Query, Depends
from typing import List, Optional
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

async def session_search_params(
       username: Optional[str] = Query(None, description="Search by username"),
       user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
       session_id : Optional[UUID] = Query(None, description="Filter by session ID"),
       ip_address: Optional[str] = Query(None, description="Filter by IP address"),
       user_agent: Optional[str] = Query(None, description="Filter by user agent"),
       token_id: Optional[UUID] = Query(None, description="Filter by token ID")
   ):
       return {
           "username": username,
           "user_id": user_id,
           "session_id": session_id,
           "ip_address": ip_address,
           "user_agent": user_agent,
           "token_id": token_id
       }

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
    set_name: Optional[str] = Query(None, description="Filter by set name"),
    card_type: Optional[str] = Query(None, description="Filter by card type"),
    rarity: Optional[str] = Query(None, description="Filter by rarity"),
    released_at: Optional[datetime] = Query(None, description="Filter by release date"),
    color: Optional[str] = Query(None, description="Filter by card color"),
    mana_cost: Optional[int] = Query(None, ge=0, description="Filter by mana cost"),
    card_id: Optional[UUID] = Query(None, description="Filter by card ID"),
    artist: Optional[str] = Query(None, description="Filter by artist"),
    artist_id: Optional[UUID] = Query(None, description="Filter by artist ID"),
    illustration_id: Optional[UUID] = Query(None, description="Filter by illustration ID"),
    power: Optional[int] = Query(None, ge=0, description="Filter by power"),
    toughness: Optional[int] = Query(None, ge=0, description="Filter by toughness"),
    flavor_text: Optional[str] = Query(None, description="Filter by flavor text"),
    card_faces: Optional[List[UUID]] = Query(None, description="Filter by card faces"),
    digital: Optional[bool] = Query(None, description="Filter by digital status")
):
    """Card search parameters"""
    return {
        "name": name,
        "set_name": set_name,
        "card_type": card_type,
        "rarity": rarity,
        "released_at": released_at,
        "mana_cost": mana_cost,
        "color": color,
        "card_id": card_id,
        #"artist": artist,
        #"artist_id": artist_id,
        #"illustration_id": illustration_id,
        #"power": power,
        #"toughness": toughness,
        #"flavor_text": flavor_text,
        #"card_faces": card_faces,
        "digital": digital,
        "card_type": card_type
    }