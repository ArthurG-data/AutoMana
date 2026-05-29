"""Step 2 — Scrape PriceCharting product catalog for all MTG sets via Playwright."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from automana.core.framework.registry import ServiceRegistry
from automana.core.repositories.app_integration.pricecharting.pc_api_repository import (
    PricechartingApiRepository,
)
from automana.core.storage import StorageService

logger = logging.getLogger(__name__)

_PC_CONSOLE_BY_UID = "https://www.pricecharting.com/console-by-uid"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_SCROLL_PAUSE_MS = 1500
_SCROLL_STABLE = 3


def _build_pc_sets(raw_items: list[dict]) -> list[dict]:
    real = [i for i in raw_items if i.get("label", "").lower() != "all" and i.get("value", "")]
    seen: set[str] = set()
    results = []
    for item in real:
        uid = item.get("value", "").strip()
        name = item.get("label", "").strip()
        if uid and name and uid not in seen:
            seen.add(uid)
            results.append({"uid": uid, "name": name})
    return sorted(results, key=lambda x: x["name"])


def _parse_price(td) -> int | None:
    if not td:
        return None
    span = td.select_one("span.js-price")
    if not span:
        return None
    raw = span.get_text(strip=True).replace("$", "").replace(",", "")
    try:
        return round(float(raw) * 100)
    except ValueError:
        return None


def _parse_set_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="games_table")
    if not table:
        return []
    rows = []
    for tr in table.select("tbody tr[data-product]"):
        a = tr.select_one("td.title a")
        if not a:
            continue
        title = a.get_text(strip=True)
        product_type = "single" if re.search(r"#\d+", title) else "sealed"
        rows.append({
            "product_id": tr["data-product"],
            "title": title,
            "product_type": product_type,
            "url": f"https://www.pricecharting.com{a['href']}",
            "ungraded_cents": _parse_price(tr.find("td", class_="used_price")),
            "grade9_cents": _parse_price(tr.find("td", class_="cib_price")),
            "psa10_cents": _parse_price(tr.find("td", class_="new_price")),
        })
    return rows


async def _scroll_to_bottom(page) -> None:
    prev_h = await page.evaluate("document.body.scrollHeight")
    stable = 0
    while stable < _SCROLL_STABLE:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(_SCROLL_PAUSE_MS)
        curr_h = await page.evaluate("document.body.scrollHeight")
        stable = stable + 1 if curr_h == prev_h else 0
        prev_h = curr_h


@ServiceRegistry.register(
    path="pricecharting.scrape_catalog",
    api_repositories=["pricecharting"],
    storage_services=["pricecharting"],
)
async def scrape_catalog(
    pricecharting_repository: PricechartingApiRepository,
    storage_service: StorageService,
    force_refresh: bool = False,
    inter_set_delay: float = 1.0,
    **kwargs: Any,
) -> dict:
    """Scrape all PriceCharting MTG set product catalogs.

    Set discovery result is cached to sets.json and reused on subsequent runs.
    Each set catalog is cached to products/{uid}.json and skipped if already present.
    Pass force_refresh=True to bust both caches.
    """
    # ── Step 1: discover sets ─────────────────────────────────────────────────
    sets_cached = await storage_service.file_exists("sets.json")
    if sets_cached and not force_refresh:
        sets_data = await storage_service.load_json("sets.json")
        pc_sets = sets_data["sets"]
        logger.info("pricecharting_sets_from_cache", extra={"count": len(pc_sets)})
    else:
        async with pricecharting_repository:
            raw = await pricecharting_repository.fetch_sets()
        pc_sets = _build_pc_sets(raw)
        await storage_service.save_json("sets.json", {
            "scraped_at": date.today().isoformat(),
            "count": len(pc_sets),
            "sets": pc_sets,
        })
        logger.info("pricecharting_sets_fetched", extra={"count": len(pc_sets)})

    # ── Step 2: scrape product catalog per set ────────────────────────────────
    total_sets = len(pc_sets)
    scraped = cached = errors = total_products = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=_USER_AGENT)
        page = await context.new_page()

        for i, set_info in enumerate(pc_sets, 1):
            uid = set_info["uid"]
            cache_key = f"products/{uid}.json"

            if await storage_service.file_exists(cache_key) and not force_refresh:
                data = await storage_service.load_json(cache_key)
                total_products += len(data.get("products", []))
                cached += 1
                continue

            try:
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                    await page.evaluate(
                        """(args) => {
                            const form = document.createElement('form');
                            form.method = 'POST';
                            form.action  = args.action;
                            const input  = document.createElement('input');
                            input.name   = 'uid';
                            input.value  = args.uid;
                            form.appendChild(input);
                            document.body.appendChild(form);
                            form.submit();
                        }""",
                        {"action": _PC_CONSOLE_BY_UID, "uid": uid},
                    )
                await _scroll_to_bottom(page)
                products = _parse_set_page(await page.content())
                await storage_service.save_json(cache_key, {
                    "scraped_at": date.today().isoformat(),
                    "uid": uid,
                    "name": set_info["name"],
                    "url": page.url,
                    "products": products,
                })
                total_products += len(products)
                scraped += 1
                logger.info(
                    "pricecharting_catalog_set_scraped",
                    extra={"i": i, "total": total_sets, "uid": uid, "products": len(products)},
                )
                await asyncio.sleep(inter_set_delay)
            except Exception:
                errors += 1
                logger.exception(
                    "pricecharting_catalog_set_failed",
                    extra={"uid": uid, "name": set_info["name"]},
                )

        await browser.close()

    logger.info(
        "pricecharting_catalog_complete",
        extra={
            "sets_discovered": total_sets,
            "scraped": scraped,
            "cached": cached,
            "errors": errors,
            "total_products": total_products,
        },
    )
    return {
        "sets_discovered": total_sets,
        "sets_scraped": scraped,
        "sets_cached": cached,
        "errors": errors,
        "total_products": total_products,
    }
