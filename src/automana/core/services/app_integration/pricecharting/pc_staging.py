"""Pure staging helpers for the PriceCharting pipeline (notebook Step 5).

Side-effect free transforms: condition/marketplace parsing, sold-at parsing,
the deterministic staging item_id, and flattening a set's sales file (joined
with the match catalog) into rows ready for ``insert_scraped_sold``.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

ENGLISH_LANGUAGE_ID = 1
DEFAULT_CURRENCY = "USD"

SOURCE_TO_MARKETPLACE = {"ebay": "EBAY-US", "tcgplayer": "TCGPLAYER"}
_DEFAULT_MARKETPLACE = "PRICECHARTING"

_COND_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"\b(near\s*mint|nm)\b", re.I), 1),
    (re.compile(r"\b(lightly\s*played|lp)\b", re.I), 2),
    (re.compile(r"\b(moderately\s*played|mp)\b", re.I), 3),
    (re.compile(r"\b(heavily\s*played|hp)\b", re.I), 4),
    (re.compile(r"\b(damaged|dmg|poor)\b", re.I), 5),
]

# Graded slabs use the condition_id dimension extended in migration 52.
_GRADE_CONDITION: dict[str, int] = {"grade7": 7, "grade8": 8, "grade9": 9, "psa10": 10}


def parse_condition(listing_title: str, grade: str) -> int:
    """Condition id from a listing. Graded rows map by grade label; ungraded
    rows are inferred from the title, defaulting to Near Mint (1)."""
    if grade != "ungraded":
        return _GRADE_CONDITION.get(grade, 1)
    for pattern, cid in _COND_PATTERNS:
        if pattern.search(listing_title):
            return cid
    return 1


def marketplace_for_source(source: str) -> str:
    return SOURCE_TO_MARKETPLACE.get(source, _DEFAULT_MARKETPLACE)


def parse_sold_at(raw: str) -> datetime | None:
    """Parse a PriceCharting sale date (``YYYY-MM-DD``) to a UTC datetime."""
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def build_item_id(product_id: str, sold_at: datetime, price_cents: int, title: str) -> str:
    """Deterministic staging id — identical inputs always produce the same id,
    so re-runs are idempotent under ``ON CONFLICT (item_id) DO NOTHING``."""
    raw = f"{product_id}-{sold_at.isoformat()}-{price_cents}-{title}"
    return "pc-" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def build_accepted_sales(sales_products: dict, catalog: dict) -> list[dict]:
    """Flatten a sales file's ``products`` map (joined with the match catalog)
    into accepted sale rows. Drops products with no catalog match and rows whose
    date cannot be parsed.

    ``sales_products``: ``{pc_product_id: {tcgplayer_id, sales: [{grade, sold_at,
    title, price_cents, source}]}}`` (as emitted by pc_sales_scrape_service).
    ``catalog``: ``{pc_product_id: match | None}`` from build_match_catalog.
    """
    accepted: list[dict] = []
    for product_id, payload in (sales_products or {}).items():
        match = catalog.get(product_id)
        if not match:
            continue
        for sale in payload.get("sales", []):
            sold_at = parse_sold_at(sale.get("sold_at"))
            if sold_at is None:
                continue
            title = sale.get("title", "")
            grade = sale.get("grade", "ungraded")
            source = sale.get("source", "unknown")
            price_cents = sale.get("price_cents")
            if price_cents is None:
                continue
            accepted.append({
                "item_id": build_item_id(product_id, sold_at, price_cents, title),
                "product_id": product_id,
                "card_version_id": match["card_version_id"],
                "title": title,
                "price_cents": price_cents,
                "currency": DEFAULT_CURRENCY,
                "condition_id": parse_condition(title, grade),
                "finish_id": match["finish_id"],
                "language_id": ENGLISH_LANGUAGE_ID,
                "sold_at": sold_at,
                "marketplace_id": marketplace_for_source(source),
            })
    return accepted
