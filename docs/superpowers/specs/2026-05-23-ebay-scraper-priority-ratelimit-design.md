# eBay Scraper: Priority Rotation + Rate-Limit Tracking

**Date:** 2026-05-23
**Issues:** #291 (watchlist rotation), #290 (Finding API rate-limit tracking)
**Status:** Approved

---

## Problem

Two gaps in `scrape_global_market` after the global-market scraper shipped:

1. **Rotation fairness (#291):** 21,964 active targets, 500 scraped per night → ~44-night full cycle. High-value cards added late are deprioritised behind older low-value entries. Pure `last_scraped_at NULLS FIRST` ordering gives every card equal weight regardless of price.

2. **Rate-limit blindness (#290):** 500 targets × 3 marketplaces = up to 1,500 Finding API calls/run. Free tier cap is 5,000/day. No budget tracking exists; when the limit is hit, each call returns error `10001` and is silently swallowed, burning quota with failed requests.

---

## Design

### #291 — Staleness-Weighted Priority Scoring

**New column:** `priority_score INTEGER NOT NULL DEFAULT 0` on `pricing.ebay_scrape_targets`.

Stores `MAX(sold_avg_cents)` from the most recent 7-day `price_observation` window for the card. Set/updated every time `refresh_scrape_targets` runs.

**Effective rank** is computed at query time — not stored — so it stays live as cards age:

```
effective_score = priority_score × (1 + days_since_last_scraped)
```

Where `days_since_last_scraped` uses `COALESCE(last_scraped_at, now() - INTERVAL '30 days')` so never-scraped cards start with a 30-day staleness bonus, guaranteeing they flush through the queue in the first few nights.

**Example scores:**
| Card value | Days since scraped | Effective score |
|-----------|-------------------|----------------|
| $50 (5 000 ¢) | 1 | 10 000 |
| $10 (1 000 ¢) | 7 | 8 000 |
| $2 (200 ¢) | 30 | 6 200 |
| $2 (200 ¢) | never | 6 200 (30-day head start) |

High-value cards dominate fresh but staleness compounds, ensuring eventual full rotation.

**Migration:** `migration_47_ebay_scrape_targets_priority.sql`
- `ALTER TABLE pricing.ebay_scrape_targets ADD COLUMN IF NOT EXISTS priority_score INTEGER NOT NULL DEFAULT 0`

**`REFRESH_SCRAPE_TARGETS` update:**
- Replace `SELECT DISTINCT cv.card_version_id, 'auto'` with `SELECT cv.card_version_id, 'auto', MAX(po.sold_avg_cents)` grouped by `cv.card_version_id`
- `ON CONFLICT DO UPDATE SET is_active = true, priority_score = EXCLUDED.priority_score`

**`GET_SCRAPE_TARGETS` update:**
```sql
SELECT card_version_id
FROM pricing.ebay_scrape_targets
WHERE is_active = true
ORDER BY
  priority_score::float
  * (1 + EXTRACT(EPOCH FROM (now() - COALESCE(last_scraped_at, now() - INTERVAL '30 days'))) / 86400.0)
DESC
LIMIT 500;
```

No service-layer changes — query change is fully transparent to `scrape_global_market`.

---

### #290 — In-Memory Rate-Limit Tracking

**Scope:** single nightly Celery beat task, single worker. In-memory counter per run is sufficient; no Redis dependency.

**Two module-level constants** in `scrape_global_market_service.py`:
```python
_API_DAILY_BUDGET = 5_000
_API_WARN_THRESHOLD = 0.80   # warn at 4 000 calls
```

**Counter placement:** incremented in the outer card loop, before each `_scrape_one_card` call (one call = one `find_completed_items` request). Uses Python `for...else/break` to propagate budget-exhaustion cleanly from the inner marketplace loop to the outer card loop without a flag variable.

**Behaviour:**
- **At 80% (4 000 calls):** `logger.warning("scrape_global_market_api_budget_warning", extra={"api_calls": ..., "budget": _API_DAILY_BUDGET})`
- **At 100% (5 000 calls):** `logger.error("scrape_global_market_api_budget_exhausted", extra={"api_calls": ..., "budget": _API_DAILY_BUDGET})` — breaks both loops immediately
- **Completion log:** `api_calls` added to existing `scrape_global_market_complete` log entry

---

## Files Changed

| File | Change |
|------|--------|
| `database/SQL/migrations/migration_47_ebay_scrape_targets_priority.sql` | ADD COLUMN priority_score |
| `repositories/app_integration/ebay/ebay_scrape_queries.py` | Update `REFRESH_SCRAPE_TARGETS` + `GET_SCRAPE_TARGETS` |
| `services/app_integration/ebay/scrape_global_market_service.py` | Rate-limit counter + loop refactor |

No router, service manager, or migration to `ebay_scrape_repository.py` needed — repository methods are unchanged (SQL is in query constants).

---

## Out of Scope

- Redis-backed cross-worker budget sharing (not needed with single beat worker; revisit if parallelised)
- Dynamic budget configuration via settings (hardcoded constant is sufficient; eBay free tier is stable)
- Raising the LIMIT 500 cap (deferred until rate budget is proven safe — Option C from #291)
