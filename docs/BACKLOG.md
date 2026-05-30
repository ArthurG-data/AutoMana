# AutoMana Backlog

_Last updated: 2026-05-24_

Items are grouped by domain. Each entry links to its source plan for full implementation detail. DONE items are omitted. Debt items from `docs/MASTER_TECHNICAL_DEBT.md` that have no dedicated plan are listed inline under the relevant domain.

---

## eBay

- **eBay Daily Sold Collection — DFC staging cleanup** — `mtgjson_uuid_alias` table and cv CTE extension shipped (migration_49); the `cleanup_staging_db` Celery step and staging truncation are not yet wired. [Plan](superpowers/plans/2026-05-24-mtgjson-dfc-uuid-staging-cleanup.md)
- **ApiBrowse connection pool leak** (P9) — `search_items()` never closes the httpx client; wrap in `async with self:`. Source: `docs/MASTER_TECHNICAL_DEBT.md` P9
- **ApiBrowse silent failure on 429** (P10) — quota exhaustion silently returns empty `CardMarketData`; add exponential backoff + re-raise. Source: `docs/MASTER_TECHNICAL_DEBT.md` P10
- **eBay `scopes.py` raw cursor in router** (M3) — `regist_scope` injects a psycopg2 cursor directly; replace with a ServiceRegistry service. Source: `docs/MASTER_TECHNICAL_DEBT.md` M3
- **`EbaySellingError` hierarchy** (S1) — three bare `Exception` catches in `listings_write_service.py` should raise typed `EbaySellingError` subclasses. Source: `docs/MASTER_TECHNICAL_DEBT.md` S1
- **`_idempotency.py` Redis wiring** (S2) — Redis client constructed ad-hoc instead of injected from ServiceRegistry startup. Source: `docs/MASTER_TECHNICAL_DEBT.md` S2
- **Apply for eBay Partner Network** (P6) — raises Finding API quota from 5k to 50k–100k/day; currently fine but hard wall at ~1,500 watchlist cards. Source: `docs/MASTER_TECHNICAL_DEBT.md` P6
- **Browse API: bad `Content-Type` and filter serialization** (P11) — GET requests send `Content-Type: application/json`; filter list not joined to comma string. Source: `docs/MASTER_TECHNICAL_DEBT.md` P11
- **Browse API: offset validation removes valid pagination** (P12) — `offset % limit != 0` guard is incorrect; remove it. Source: `docs/MASTER_TECHNICAL_DEBT.md` P12

---

## Collections

_(No pending plan items. Known debt below.)_

- **Wishlist demand-signal correlation** (RN2) — accumulate wishlist snapshots over time, then correlate wishlist add-rate with price movement (Gap 6 from MTG quant research). Source: `docs/domain/MTG_QUANT_RESEARCH.md`

---

## Shopify

_(No pending plan items. Known debt below.)_

- **`market_repository.py` indentation bug** (I5 from abstract-wrappers plan) — `update` method's execute call is at class level, silently no-ops if `set_clauses` is empty. Source: `docs/superpowers/plans/2026-05-24-abstract-db-repo-wrappers.md` I5
- **`ProductRepository.__init__` executor default** (I3 from abstract-wrappers plan) — `executor: None` is a type annotation not a default; `ProductRepository(conn)` raises `TypeError`. Source: `docs/superpowers/plans/2026-05-24-abstract-db-repo-wrappers.md` I3

---

## Infrastructure / API Debt

- **`auth_service.py` raises `HTTPException`** (H2) — service layer must not raise HTTP exceptions; return `None` on bad credentials. Source: `docs/MASTER_TECHNICAL_DEBT.md` H2
- **`password_reset_service.py` raises `HTTPException`** (H3) — raise domain exception, translate to 400 in the router. Source: `docs/MASTER_TECHNICAL_DEBT.md` H3
- **Four independent password-hashing implementations** (H4) — raw bcrypt vs passlib bcrypt; designate `core/utils/get_hash_password.py` as canonical and remove duplicates. Source: `docs/MASTER_TECHNICAL_DEBT.md` H4
- **`sort_params` default `sort_by="card_name"` leaks** (M5) — shared dependency silently sorts non-card endpoints by card name. Source: `docs/MASTER_TECHNICAL_DEBT.md` M5
- **`user_repository.py:add_many` uses psycopg2 `%s` placeholders** (L2) — delete if unused, or rewrite with asyncpg `$N` and `executemany`. Source: `docs/MASTER_TECHNICAL_DEBT.md` L2
- **`AsyncpgExceptionHandler` never called** (L3) — stored in `app.state` but every router has its own naked `except Exception: raise HTTPException(500)`. Source: `docs/MASTER_TECHNICAL_DEBT.md` L3
- **Duplicated `_AUTH_ERRORS` / `_ERRORS` dicts across routers** (L4) — extract to a shared `COMMON_RESPONSES` dict. Source: `docs/MASTER_TECHNICAL_DEBT.md` L4
- **Redis cache: `KEYS`-based invalidation is O(n)** (I2) — replace with `SCAN` cursor for production scale. Source: `docs/MASTER_TECHNICAL_DEBT.md` I2
- **MTGStock pipeline: ~11-hour duration** (P2) — far beyond a nightly window; needs profiling and batching improvements. Source: `docs/MASTER_TECHNICAL_DEBT.md` P2
- **`load_staging_prices_batched` issues COMMIT inside a loop** (P3) — architecturally incorrect stored procedure; prevents transactional safety. Source: `docs/MASTER_TECHNICAL_DEBT.md` P3

---

## Testing

- **Service layer unit test coverage** (T1) — Phases 2, 3 (user/role), and 4 (MTGJson/Scryfall ETL) are all pending; only Phase 1 (pure logic) shipped. Source: `docs/MASTER_TECHNICAL_DEBT.md` T1
- **`user_repository.py` reject-log missing fields** (R1) — rejects don't include `scryfall_id`, `card_name`, `set_abbr`, or `collector_number`, making diagnosis hard. Source: `docs/MASTER_TECHNICAL_DEBT.md` R1

---

## Research

- **MTG Repeat-Sales Index — benchmarking section** (RN1) — notebook Methods A/B/C complete; Section 8 (S&P 500 total return, CPI-adjusted return, Pokémon/sports-card comparisons) is still TODO. Source: `docs/MASTER_TECHNICAL_DEBT.md` RN1
- **MTGStock: `priority_score` watchlist cap at 500 cards** (P5) — cap may need raising once production throughput is measured beyond ~500 cards. Source: `docs/MASTER_TECHNICAL_DEBT.md` P5
- **Scryfall integrity: 1,031 sets with no icon** (P13) — ongoing post-pipeline sanity warning; impact not yet measured. Source: `docs/MASTER_TECHNICAL_DEBT.md` P13

---

## Production Deployment

- **VPS database hosting** — 252 GB DB can't fit on current VPS; Sydney-region provider needed. Current state: VPS is live and running, DB served via FRP tunnel from local machine. Source: [Plan](superpowers/plans/2026-05-21-production-deployment.md) / memory `project_production_deployment.md`
