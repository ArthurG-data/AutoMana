# backend/dependancies/query_deps.py
from fastapi import Query, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

class PaginationParams(BaseModel):
    limit: int
    offset: int

class SortParams(BaseModel):
    sort_by: str
    sort_order: str

class DateRangeParams(BaseModel):
    created_after: Optional[datetime]
    created_before: Optional[datetime]

async def pagination_params(
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip")
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)

async def sort_params(
    sort_by: str = Query("card_name", description="Field to sort by"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order")
) -> SortParams:
    return SortParams(sort_by=sort_by, sort_order=sort_order)

async def date_range_params(
    created_after: Optional[datetime] = Query(None, description="Filter items created after this date"),
    created_before: Optional[datetime] = Query(None, description="Filter items created before this date")
) -> DateRangeParams:
    return DateRangeParams(created_after=created_after, created_before=created_before)

async def session_search_params(
    username: Optional[str] = Query(None, description="Search by username"),
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    session_id: Optional[UUID] = Query(None, description="Filter by session ID"),
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
        "token_id": token_id,
    }

async def user_search_params(
    username: Optional[str] = Query(None, description="Search by username"),
    email: Optional[str] = Query(None, description="Search by email (admin only)"),
    full_name: Optional[str] = Query(None, description="Search by full name"),
    search_query: Optional[str] = Query(None, min_length=2, description="General search across username and full name"),
    disabled: Optional[bool] = Query(None, description="Filter by active status"),
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
):
    return {
        "username": username,
        "email": email,
        "full_name": full_name,
        "search_query": search_query,
        "disabled": disabled,
        "user_id": user_id,
    }

async def card_search_params(
    q: Optional[str] = Query(None, description="Search query for card name or oracle text"),
    name: Optional[str] = Query(None, description="Filter by card name"),
    set_name: Optional[str] = Query(None, description="Filter by set name"),
    set_code: Optional[str] = Query(None, alias="set", description="Filter by exact set code (e.g. 'mkm')"),
    card_type: Optional[str] = Query(None, description="Filter by card type"),
    rarity: Optional[str] = Query(None, description="Filter by rarity"),
    colors: Optional[List[str]] = Query(None, alias="color", description="Filter by card color (repeatable: ?color=Blue&color=Green)"),
    mana_cost: Optional[int] = Query(None, ge=0, description="Filter by mana cost"),
    card_id: Optional[UUID] = Query(None, description="Filter by card ID"),
    unique_card_id: Optional[UUID] = Query(None, description="Filter by stable unique card identity (returns all versions/printings of a single logical card)"),
    artist: Optional[str] = Query(None, description="Filter by artist"),
    digital: bool = Query(False, description="Filter by digital status (default excludes MTGO/Arena-only cards)"),
    oracle_text: Optional[str] = Query(None, description="Filter by oracle text (full-text search)"),
    format: Optional[str] = Query(None, description="Filter by format legality (e.g. 'standard', 'modern')"),
    layout: Optional[str] = Query(None, description="Filter by layout type (e.g. 'normal', 'token', 'saga')"),
    promo_type: Optional[List[str]] = Query(None, description="Filter by promo type (repeatable: ?promo_type=prerelease&promo_type=buyabox)"),
    collapse: bool = Query(False, description="Collapse results to one representative per (unique_card_id, set_code). Returns version_count on each tile."),
    finish: Optional[str] = Query(None, description="Filter by finish (nonfoil, foil, etched, surge_foil, ripple_foil, rainbow_foil)"),
    frame_effects: Optional[List[str]] = Query(None, alias="frame_effect", description="Filter by frame treatment (repeatable: ?frame_effect=borderless&frame_effect=showcase)"),
):
    return {
        "name": q or name,
        "set_name": set_name,
        "set_code": set_code,
        "rarity": rarity,
        "mana_cost": mana_cost,
        "colors": colors,
        "card_id": card_id,
        "unique_card_id": unique_card_id,
        "artist": artist,
        "digital": digital,
        "card_type": card_type,
        "oracle_text": oracle_text,
        "format": format,
        "layout": layout,
        "promo_type": promo_type,
        "collapse": collapse,
        "finish": finish,
        "frame_effects": frame_effects,
    }
