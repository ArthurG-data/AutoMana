from __future__ import annotations

import json
import logging
from typing import Callable

import asyncpg

logger = logging.getLogger(__name__)


def _rows_to_json(rows: list[asyncpg.Record]) -> str:
    return json.dumps([dict(r) for r in rows], default=str)


async def _search_cards(conn: asyncpg.Connection, *, query: str, limit: int = 10) -> str:
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (v.card_name)
            v.card_name, v.set_code, v.mana_cost, v.type_line, v.rarity_name
        FROM card_catalog.v_card_versions_complete v
        WHERE v.lang = 'en'
          AND (
            v.search_vector @@ websearch_to_tsquery('english', $1)
            OR v.card_name ILIKE '%' || $1 || '%'
          )
        ORDER BY v.card_name,
            ts_rank_cd(v.search_vector, websearch_to_tsquery('english', $1)) DESC
        LIMIT $2
        """,
        query,
        limit,
    )
    return _rows_to_json(rows)


async def _get_card_prices(
    conn: asyncpg.Connection,
    *,
    card_name: str,
    set_code: str | None = None,
) -> str:
    base = """
        SELECT ucr.card_name, s.set_code, cf.code AS finish,
               po.list_avg_cents, po.list_low_cents, dp.code AS provider, po.ts_date
        FROM pricing.price_observation po
        JOIN pricing.source_product sp USING (source_product_id)
        JOIN pricing.mtg_card_products mcp USING (product_id)
        JOIN card_catalog.card_version cv USING (card_version_id)
        JOIN card_catalog.unique_cards_ref ucr USING (unique_card_id)
        JOIN card_catalog.sets s ON s.set_id = cv.set_id
        JOIN card_catalog.card_finished cf USING (finish_id)
        JOIN pricing.data_provider dp USING (data_provider_id)
        WHERE ucr.card_name ILIKE $1
    """
    if set_code:
        rows = await conn.fetch(base + " AND s.set_code = $2 ORDER BY po.ts_date DESC LIMIT 20", card_name, set_code)
    else:
        rows = await conn.fetch(base + " ORDER BY po.ts_date DESC LIMIT 20", card_name)
    return _rows_to_json(rows)


async def _get_collection_summary(conn: asyncpg.Connection, *, user_id: str) -> str:
    rows = await conn.fetch(
        """
        SELECT COUNT(*) AS total_cards, COUNT(DISTINCT ci.unique_card_id) AS unique_cards
        FROM user_collection.collections c
        JOIN user_collection.collection_items ci USING (collection_id)
        WHERE c.user_id = $1::uuid AND c.is_active = true
        """,
        user_id,
    )
    return _rows_to_json(rows)


async def _get_active_listings(
    conn: asyncpg.Connection,
    *,
    app_code: str,
    limit: int = 20,
) -> str:
    rows = await conn.fetch(
        """
        SELECT listing_id, title, price, quantity, condition, listed_at
        FROM app_integration.ebay_active_listings
        WHERE app_code = $1
        ORDER BY listed_at DESC
        LIMIT $2
        """,
        app_code,
        limit,
    )
    return _rows_to_json(rows)


async def _get_sold_orders(
    conn: asyncpg.Connection,
    *,
    app_code: str,
    days: int = 7,
    limit: int = 20,
) -> str:
    rows = await conn.fetch(
        """
        SELECT order_id, local_status, tracking_number, carrier_code, shipped_at
        FROM app_integration.ebay_order_status
        WHERE app_code = $1
          AND shipped_at >= now() - ($2 || ' days')::interval
        ORDER BY shipped_at DESC
        LIMIT $3
        """,
        app_code,
        str(days),
        limit,
    )
    return _rows_to_json(rows)


async def _get_market_comps(
    conn: asyncpg.Connection,
    *,
    card_name: str,
    condition: str | None = None,
) -> str:
    rows = await conn.fetch(
        """
        SELECT ucr.card_name, s.set_code, cf.code AS finish,
               po.list_avg_cents, po.list_low_cents, po.sold_avg_cents,
               dp.code AS provider, po.ts_date
        FROM pricing.price_observation po
        JOIN pricing.source_product sp USING (source_product_id)
        JOIN pricing.mtg_card_products mcp USING (product_id)
        JOIN card_catalog.card_version cv USING (card_version_id)
        JOIN card_catalog.unique_cards_ref ucr USING (unique_card_id)
        JOIN card_catalog.sets s ON s.set_id = cv.set_id
        JOIN card_catalog.card_finished cf USING (finish_id)
        JOIN pricing.data_provider dp USING (data_provider_id)
        WHERE ucr.card_name ILIKE $1
        ORDER BY po.ts_date DESC
        LIMIT 30
        """,
        card_name,
    )
    return _rows_to_json(rows)


async def _get_listings_needing_action(conn: asyncpg.Connection, **kwargs) -> str:
    return json.dumps({"status": "not_implemented", "message": "Coming soon"})


async def _get_card_buy_recommendations(conn: asyncpg.Connection, **kwargs) -> str:
    return json.dumps({"status": "not_implemented", "message": "Coming soon"})


TOOL_MAP: dict[str, Callable] = {
    "search_cards": _search_cards,
    "get_card_prices": _get_card_prices,
    "get_collection_summary": _get_collection_summary,
    "get_active_listings": _get_active_listings,
    "get_sold_orders": _get_sold_orders,
    "get_market_comps": _get_market_comps,
    "get_listings_needing_action": _get_listings_needing_action,
    "get_card_buy_recommendations": _get_card_buy_recommendations,
}

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_cards",
            "description": "Full-text search Magic cards by name or oracle text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms"},
                    "limit": {"type": "integer", "default": 10, "description": "Max results"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_card_prices",
            "description": "Retrieve latest price observations for a Magic card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {"type": "string"},
                    "set_code": {"type": "string", "description": "3-letter set code (optional)"},
                },
                "required": ["card_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_collection_summary",
            "description": "Summarise a user's card collection by set.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the user"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_listings",
            "description": "List active eBay listings for an app.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_code": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["app_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sold_orders",
            "description": "Retrieve recent eBay sold orders for an app.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_code": {"type": "string"},
                    "days": {"type": "integer", "default": 7},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["app_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_comps",
            "description": "Retrieve market comparable prices (eBay sold, TCGPlayer) for a card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {"type": "string"},
                    "condition": {"type": "string", "description": "e.g. NM, LP, MP (optional)"},
                },
                "required": ["card_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_listings_needing_action",
            "description": "Identify listings that need repricing or attention. (Coming soon)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_card_buy_recommendations",
            "description": "Suggest cards to buy based on price trends. (Coming soon)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
