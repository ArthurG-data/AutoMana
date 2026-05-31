"""Step 3 — Scrape individual card sold-listing pages from PriceCharting (httpx)."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import Any
from urllib.parse import unquote

from bs4 import BeautifulSoup

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.app_integration.pricecharting.pc_api_repository import (
    PricechartingApiRepository,
)
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)

_GRADE_TABLES: dict[str, str] = {
    "completed-auctions-used": "ungraded",
    "completed-auctions-cib": "grade7",
    "completed-auctions-new": "grade8",
    "completed-auctions-graded": "grade9",
    "completed-auctions-manual-only": "psa10",
}


def _detect_source(title_td) -> str:
    """Detect the marketplace a PriceCharting sold row came from.

    PriceCharting tags each completed-sale row's title cell with a ``[TCGPlayer]``
    or ``[eBay]`` marker; fall back to the row link's href when the marker is absent.
    """
    text = title_td.get_text()
    if "[TCGPlayer]" in text:
        return "tcgplayer"
    if "[eBay]" in text:
        return "ebay"
    link = title_td.find("a")
    if link:
        href = link.get("href", "")
        if "tcgplayer" in href:
            return "tcgplayer"
        if "ebay" in href:
            return "ebay"
    return "unknown"


def _extract_tcg_product_id(node) -> str | None:
    """First ``/product/<id>`` found in any link href under ``node`` (decoded)."""
    for a in node.find_all("a"):
        m = re.search(r"/product/(\d+)", unquote(a.get("href", "")))
        if m:
            return m.group(1)
    return None


def _consensus_tcg_id(page_level: str | None, per_listing: list[str]) -> tuple[str | None, int]:
    """Resolve the product's TCGPlayer id from the per-listing votes, falling
    back to the page-level link. Returns (id, vote_count).

    The individual TCGPlayer-sourced sold rows each link to the product, so a
    majority vote across them is more robust than the single page-level link
    (and still works when that link is absent). vote_count feeds match certainty.
    """
    if per_listing:
        counts: dict[str, int] = {}
        for pid in per_listing:
            counts[pid] = counts.get(pid, 0) + 1
        winner = max(counts, key=lambda k: counts[k])
        return winner, counts[winner]
    return page_level, 0


def _parse_sales_page(html: str, product_id: str) -> dict:
    """Parse a PriceCharting card page, returning sales rows and TCGPlayer ID."""
    soup = BeautifulSoup(html, "html.parser")

    tcg_link = soup.select_one("a.js-tcgplayer-completed-sale")
    page_tcg_id: str | None = None
    if tcg_link and tcg_link.get("href"):
        # The href is an affiliate redirect with the real TCGPlayer product URL
        # percent-encoded in its `u=` param — decode before matching /product/{id}.
        m = re.search(r"/product/(\d+)", unquote(tcg_link["href"]))
        if m:
            page_tcg_id = m.group(1)

    sales: list[dict] = []
    per_listing_tcg: list[str] = []
    for css_class, grade in _GRADE_TABLES.items():
        # Each grade section has two divs with the same class: a tab label (carries
        # "tab" in its class list) and the content panel that holds the data table.
        candidates = soup.find_all("div", class_=css_class)
        container = next((c for c in candidates if "tab" not in c.get("class", [])), None)
        if not container:
            continue
        table = container.find("table", class_="hoverable-rows")
        if not table:
            continue
        for tr in table.select("tbody tr"):
            # PriceCharting rows are: date | image | title | numeric(price) | ...
            # The price lives in td.numeric > span.js-price — NOT a positional cell.
            date_td = tr.find("td", class_="date")
            title_td = tr.find("td", class_="title")
            price_td = tr.find("td", class_="numeric")
            if not (date_td and title_td and price_td):
                continue

            price_span = price_td.find("span", class_="js-price")
            price_text = price_span.get_text(strip=True) if price_span else price_td.get_text(strip=True)
            price_raw = price_text.replace("$", "").replace(",", "")
            try:
                price_cents = round(float(price_raw) * 100)
            except ValueError:
                continue

            link = title_td.find("a")
            listing_title = link.get_text(strip=True) if link else title_td.get_text(strip=True)

            source = _detect_source(title_td)
            if source == "tcgplayer":
                row_tcg = _extract_tcg_product_id(tr)
                if row_tcg:
                    per_listing_tcg.append(row_tcg)

            sales.append({
                "grade": grade,
                "sold_at": date_td.get_text(strip=True),
                "title": listing_title,
                "price_cents": price_cents,
                "source": source,
            })

    tcg_id, tcg_votes = _consensus_tcg_id(page_tcg_id, per_listing_tcg)
    return {
        "product_id": product_id,
        "tcgplayer_id": tcg_id,
        "tcgplayer_id_votes": tcg_votes,
        "sales": sales,
    }


@ServiceRegistry.register(
    path="pricecharting.scrape_sales",
    api_repositories=["pricecharting"],
    storage_services=["pricecharting"],
)
async def scrape_sales(
    pricecharting_repository: PricechartingApiRepository,
    storage_service: StorageService,
    force_refresh: bool = False,
    inter_card_delay: float = 0.5,
    **kwargs: Any,
) -> dict:
    """Scrape sold-listing pages for all single products in the cached catalog.

    Requires pricecharting.scrape_catalog to have run first (sets.json +
    products/{uid}.json must exist). Sales are cached per set to
    sales/{uid}.json and skipped on subsequent runs unless force_refresh=True.
    """
    if not await storage_service.file_exists("sets.json"):
        logger.warning("pricecharting_sales_no_sets_file")
        return {"sets_processed": 0, "cards_scraped": 0, "cards_cached": 0, "errors": 0}

    sets_data = await storage_service.load_json("sets.json")
    pc_sets: list[dict] = sets_data.get("sets", [])

    sets_processed = cards_scraped = cards_cached = errors = 0

    async with pricecharting_repository:
        for set_info in pc_sets:
            uid = set_info["uid"]
            sales_key = f"sales/{uid}.json"

            if await storage_service.file_exists(sales_key) and not force_refresh:
                cards_cached += 1
                sets_processed += 1
                continue

            catalog_key = f"products/{uid}.json"
            if not await storage_service.file_exists(catalog_key):
                logger.warning(
                    "pricecharting_sales_missing_catalog",
                    extra={"uid": uid, "name": set_info["name"]},
                )
                continue

            catalog = await storage_service.load_json(catalog_key)
            singles = [p for p in catalog.get("products", []) if p["product_type"] == "single"]

            set_sales: dict[str, dict] = {}
            for product in singles:
                product_id = product["product_id"]
                try:
                    html = await pricecharting_repository.fetch_sales_html(product["url"])
                    set_sales[product_id] = _parse_sales_page(html, product_id)
                    cards_scraped += 1
                except Exception:
                    errors += 1
                    logger.exception(
                        "pricecharting_sales_card_failed",
                        extra={"uid": uid, "product_id": product_id},
                    )
                await asyncio.sleep(inter_card_delay)

            await storage_service.save_json(sales_key, {
                "scraped_at": date.today().isoformat(),
                "uid": uid,
                "name": set_info["name"],
                "products": set_sales,
            })
            sets_processed += 1
            logger.info(
                "pricecharting_sales_set_complete",
                extra={"uid": uid, "singles": len(singles), "errors": errors},
            )

    logger.info(
        "pricecharting_sales_complete",
        extra={
            "sets_processed": sets_processed,
            "cards_scraped": cards_scraped,
            "cards_cached": cards_cached,
            "errors": errors,
        },
    )
    return {
        "sets_processed": sets_processed,
        "cards_scraped": cards_scraped,
        "cards_cached": cards_cached,
        "errors": errors,
    }
