# eBay Service Integration Plan

**Created:** 2026-04-18  
**Status:** Pending implementation  
**Branch target:** `feature/ebay_integration` (to be created from `main`)

---

## Goal

Integrate existing eBay service functions into a coherent service layer enabling automation of:
1. Listing creation
2. Listing updates
3. Listing deletion
4. Market price collection (active + sold)

---

## What Already Exists (keep, don't rebuild)

| Layer | File | Notes |
|---|---|---|
| Auth services | `core/services/app_integration/ebay/auth_services.py` | Functional, registered |
| Auth repository | `core/repositories/app_integration/ebay/auth_repository.py` | Has duplicate `get_access_from_refresh` (sync redefining async) — fix |
| OAuth API repository | `core/repositories/app_integration/ebay/ApiAuth_repository.py` | Functional |
| Selling API repository | `core/repositories/app_integration/ebay/ApiSelling_repository.py` | Functional but unregistered; leaks `payload: dict` into repo layer |
| Browse API repository | `core/repositories/app_integration/ebay/ApiBrowse_repository.py` | Functional |
| `EbayApiClient` base | `core/repositories/app_integration/ebay/EbayApiRepository.py` | Solid base — extend, don't duplicate |
| Selling dispatcher | `core/services/app_integration/ebay/selling_services.py` | Unregistered; god-dispatcher anti-pattern — rewrite |
| Browsing service | `core/services/app_integration/ebay/browsing_services.py` | Registered, keep |
| DB schema — auth | `database/SQL/schemas/05_ebay.sql` | apps, tokens, scopes, oauth log |
| DB schema — prices | `database/SQL/schemas/06_prices.sql` | `pricing.price_observation` hypertable; `'ebay'` already in `price_source` |
| Pipeline harness | `worker/tasks/pipelines.py` + `ops.pipeline_services` | Reuse `chain(run_service.s(...))` pattern verbatim |

---

## Problems to Fix First

1. `handle_selling_request` is an **unregistered god dispatcher** — split into 4 registered services
2. `EbaySellingRepository` takes `payload: dict` — leaks service logic into repo layer; refactor to typed args
3. `worker/tasks/ebay.py` is **100% commented-out dead code** — replace entirely
4. `auth_repository.py` has a duplicate `get_access_from_refresh` (sync redefines async)
5. `selling` repo registered as `"selling"` but called as `selling_repository` — name mismatch
6. No price-collection service exists at all

---

## Target Module Map

```
src/automana/core/
├── services/app_integration/ebay/
│   ├── auth_services.py                  [keep]
│   ├── selling_services.py               [REWRITE — split into 4+ registered services]
│   ├── browsing_services.py              [keep]
│   ├── price_collection_services.py      [NEW]
│   └── token_resolver.py                 [NEW — shared _resolve_token() helper]
│
├── repositories/app_integration/ebay/
│   ├── ApiSelling_repository.py          [REFACTOR — typed args]
│   ├── ApiBrowse_repository.py           [EXTEND — add search_active_listings_for_card()]
│   ├── listing_repository.py             [NEW — local mirror of eBay listings]
│   └── price_observation_repository.py   [NEW — write-side for pricing.price_observation]
│
├── models/ebay/
│   ├── selling.py                        [NEW — CreateListingRequest, UpdateListingRequest, etc.]
│   └── pricing.py                        [NEW — EbayPriceObservation, MarketDataQuery]
│
└── service_registry.py                   [ADD 2 DB repos + 1 named storage]

src/automana/worker/tasks/
├── pipelines.py                          [ADD 2 pipelines]
├── ebay.py                               [REWRITE as trigger task module]
└── celeryconfig.py                       [ADD Beat entries]

src/automana/api/routers/integrations/ebay/
├── ebay_selling.py                       [REWRITE — call typed services per action]
└── ebay_pricing.py                       [NEW]

src/automana/database/SQL/migrations/
└── 15_ebay_listing_local_state.sql       [NEW]
```

---

## Registered Services

All follow `@ServiceRegistry.register(path, db_repositories=[...], api_repositories=[...])` and return `dict` for Celery chain composition.

### Selling Lifecycle (`selling_services.py`)

```python
"integrations.ebay.selling.create_listing"
    db_repositories=["auth", "ebay_listing"], api_repositories=["selling"]
    args: user_id, app_code, item: ItemModel, marketplace_id="15", verify=False
    returns: {"item_id": str, "fees": {...}, "status": "active"|"verified"}

"integrations.ebay.selling.update_listing"
    db_repositories=["auth", "ebay_listing"], api_repositories=["selling"]
    args: user_id, app_code, item: ItemModel, marketplace_id="15"
    returns: {"item_id": str, "status": "updated"}

"integrations.ebay.selling.delete_listing"
    db_repositories=["auth", "ebay_listing"], api_repositories=["selling"]
    args: user_id, app_code, item_id: str, ending_reason="NotAvailable", verify=False
    returns: {"item_id": str, "status": "ended"}

"integrations.ebay.selling.get_active_listings"
    db_repositories=["auth"], api_repositories=["selling"]
    args: user_id, app_code, limit=50, offset=0, marketplace_id="15"
    returns: {"listings": [...], "total": int}

"integrations.ebay.selling.get_order_history"
    db_repositories=["auth"], api_repositories=["selling"]
    args: user_id, app_code, limit=50, offset=0, days_back=728
    returns: {"orders": [...], "total": int}

"integrations.ebay.selling.sync_local_listings"  # reconciliation
    db_repositories=["auth", "ebay_listing"], api_repositories=["selling"]
    args: user_id, app_code
    returns: {"synced": int, "orphans": int, "drift": int}
```

### Price Collection (`price_collection_services.py`)

```python
"integrations.ebay.pricing.resolve_target_cards"
    db_repositories=["card", "user_collection", "ops"]
    args: ingestion_run_id, scope="collection", limit=None
    returns: {"targets": [{"card_version_id", "name", "set_code", "collector_number"}, ...]}

"integrations.ebay.pricing.collect_active_listings"
    db_repositories=["auth", "ops"], api_repositories=["search"]
    args: ingestion_run_id, targets, user_id, app_code, batch_size=50
    returns: {"observations_path": "/data/ebay/raw/{run_id}/active.jsonl"}

"integrations.ebay.pricing.collect_sold_listings"
    db_repositories=["auth", "ops"], api_repositories=["selling"]
    args: ingestion_run_id, targets, user_id, app_code, days_back=30
    returns: {"observations_path": "/data/ebay/raw/{run_id}/sold.jsonl"}

"integrations.ebay.pricing.load_observations"
    db_repositories=["price_observation", "ops"]
    args: ingestion_run_id, observations_path, source_code="ebay"
    returns: {"inserted": int, "skipped": int}

"integrations.ebay.pricing.rollup_daily"
    db_repositories=["price_observation", "ops"]
    args: ingestion_run_id
    returns: {"rolled_up_rows": int}
```

---

## Repository Contracts

### `EbaySellingRepository` (refactor)

```python
async def create_listing(*, item: ItemModel, token: str, marketplace_id="15", verify=False) -> dict
async def update_listing(*, item: ItemModel, token: str, marketplace_id="15") -> dict
async def delete_listing(*, item_id: str, token: str, marketplace_id="15", ending_reason="NotAvailable", verify=False) -> dict
async def get_active(*, token: str, marketplace_id="15", entries_per_page=50, page_number=1) -> dict
async def get_order_history(*, token: str, start: datetime, end: datetime, limit: int, offset: int) -> dict
async def get_sold_items(*, token: str, days_back: int, seller_id: str | None = None) -> dict  # NEW
```

### `EbayListingRepository` (new — DB)

```python
async def upsert_local_state(*, user_id, app_code, item_id, sku, status, card_version_id, price_cents, quantity, raw_payload) -> None
async def get_active_for_user(user_id, app_code) -> list[dict]
async def mark_ended(item_id, ended_at, ending_reason) -> None
async def find_by_card_version(card_version_id) -> list[dict]
```

### `EbayPriceObservationRepository` (new — DB)

```python
async def copy_observations(jsonl_path: Path, source_id: int) -> int  # COPY ... FROM STDIN
async def get_recent_for_card(card_version_id, days) -> list[dict]
async def rollup_daily(run_id: int) -> int
```

### `EbayBrowseAPIRepository` extension

```python
async def search_active_listings_for_card(*, query, condition_ids, category_id="183454", sort="price", limit=100, headers) -> dict
```

---

## New DB Migration: `15_ebay_listing_local_state.sql`

```sql
BEGIN;

CREATE TABLE IF NOT EXISTS app_integration.ebay_listing (
    listing_id       BIGSERIAL PRIMARY KEY,
    user_id          UUID NOT NULL REFERENCES user_management.users(unique_id) ON DELETE CASCADE,
    app_id           TEXT NOT NULL REFERENCES app_integration.app_info(app_id) ON DELETE CASCADE,
    ebay_item_id     TEXT NOT NULL,
    sku              TEXT,
    card_version_id  UUID REFERENCES card_catalog.card_version(id),
    marketplace_id   TEXT NOT NULL DEFAULT '15',
    status           TEXT NOT NULL CHECK (status IN ('draft','active','ended','error')),
    price_cents      INTEGER NOT NULL CHECK (price_cents >= 0),
    quantity         INTEGER NOT NULL CHECK (quantity >= 0),
    last_synced_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at         TIMESTAMPTZ,
    ending_reason    TEXT,
    raw_payload      JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (app_id, ebay_item_id)
);

CREATE INDEX idx_ebay_listing_user_status ON app_integration.ebay_listing (user_id, status) WHERE status = 'active';
CREATE INDEX idx_ebay_listing_card_version ON app_integration.ebay_listing (card_version_id) WHERE card_version_id IS NOT NULL;

COMMIT;
```

No new schema needed for prices — `pricing.price_observation` + `price_source('ebay')` already exist.

---

## Celery Pipelines

### `ebay_listing_reconcile_pipeline`

```python
chain(
    run_service.s("ops.pipeline_services.start_run", pipeline_name="ebay_reconcile", ...),
    run_service.s("integrations.ebay.selling.sync_local_listings", user_id=..., app_code=...),
    run_service.s("ops.pipeline_services.finish_run", status="success"),
)
```

Beat: every hour at `:15` — fan-out per active `(user_id, app_code)` via dispatcher task.

### `ebay_market_data_pipeline`

```python
chain(
    run_service.s("ops.pipeline_services.start_run", pipeline_name="ebay_market_data", ...),
    run_service.s("integrations.ebay.pricing.resolve_target_cards", scope=scope),
    run_service.s("integrations.ebay.pricing.collect_active_listings", user_id=..., app_code=...),
    run_service.s("integrations.ebay.pricing.collect_sold_listings", user_id=..., app_code=..., days_back=30),
    run_service.s("integrations.ebay.pricing.load_observations"),
    run_service.s("integrations.ebay.pricing.rollup_daily"),
    run_service.s("ops.pipeline_services.finish_run", status="success"),
)
```

Beat: nightly at 04:30 local. **No `autoretry_for`** — project rule; retries at `run_service` level.

---

## OAuth / Token Concerns

1. **Access token TTL ~2h** — `_resolve_token()` must refresh inside a DB transaction to prevent concurrent worker double-refresh
2. **Refresh token TTL 18 months** — on revocation, surface `EbayTokenRevokedException` and emit ops alert; user must re-auth
3. **Per-app, per-user scoping** — all services take `(user_id, app_code)`; pipelines fan-out per active integration
4. **Sandbox vs production** — `app_info.environment` drives `_get_base_url()`; `ServiceManager` must pass `environment=` when constructing API repos
5. **Rate limits** — Trading API ~5k/day; Browse ~5k/day; sold listings much stricter. Add `_throttle.py` with per-`(app_id, endpoint)` `asyncio.Semaphore`
6. **Create idempotency** — use eBay's `UUID` field on `AddFixedPriceItem`; generate if missing, store on local mirror so retries don't double-list

---

## Implementation Order

Build each step independently — each leaves the system working:

| # | Step | Files touched |
|---|---|---|
| 1 | Refactor `ApiSelling_repository.py` to typed args | `ApiSelling_repository.py` |
| 2 | Split `handle_selling_request` into 4 registered services + `token_resolver.py` | `selling_services.py`, `token_resolver.py` |
| 3 | Update `ebay_selling.py` router to call typed services | `routers/.../ebay_selling.py` |
| 4 | Migration + `EbayListingRepository` | `15_ebay_listing_local_state.sql`, `listing_repository.py` |
| 5 | `sync_local_listings` service + `ebay_listing_reconcile_pipeline` + Beat entry | `selling_services.py`, `pipelines.py`, `celeryconfig.py` |
| 6 | Price collection — active listings only | `price_collection_services.py`, `price_observation_repository.py` |
| 7 | `ebay_market_data_pipeline` + Beat entry | `pipelines.py`, `celeryconfig.py` |
| 8 | Add `collect_sold_listings` + `rollup_daily` | `price_collection_services.py` |
| 9 | Replace `worker/tasks/ebay.py` with trigger module | `ebay.py` |
| 10 | Delete all dead commented code | various |
