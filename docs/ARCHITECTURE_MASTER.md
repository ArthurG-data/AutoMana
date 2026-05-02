# AutoMana Architecture Master

Complete system overview, data residency mapping, and navigation to all specialized documentation.

## Quick Navigation

- **Frontend Documentation:** [See docs/FRONTEND.md](FRONTEND.md) — React app architecture
- **Backend Documentation:** [See docs/BACKEND.md](BACKEND.md) — FastAPI server architecture

---

## Table of Contents

1. System Overview Diagram
2. Data Residency Map
3. Cross-System Data Flows
4. Critical Paths & Dependencies
5. Documentation Navigator

---

## System Overview Diagram

```mermaid
graph TB
    subgraph Client["Client Layer"]
        Browser["Browser"]
    end
    
    subgraph Network["Network Layer"]
        Nginx["nginx Reverse Proxy<br/>(80/443 TLS)")
    end
    
    subgraph Backend["Backend Layer"]
        FastAPI["FastAPI Server<br/>(async handlers)"]
        ServiceMgr["ServiceManager<br/>(DI + Service Registry)"]
    end
    
    subgraph Data["Data Layer"]
        PG["PostgreSQL<br/>+ TimescaleDB<br/>+ pgvector"]
        Redis["Redis<br/>(Cache, Queue)"]
    end
    
    subgraph External["External Integrations"]
        eBay["eBay API"]
        Shopify["Shopify API"]
        Scryfall["Scryfall Bulk Data"]
        MTGJson["MTGJson API"]
        MTGStock["MTGStock API"]
    end
    
    subgraph Jobs["Background Processing"]
        Celery["Celery Workers"]
        Beat["Celery Beat<br/>(Scheduler)"]
    end
    
    Browser -->|HTTP/HTTPS| Nginx
    Nginx -->|HTTP| FastAPI
    FastAPI -->|Query/Command| ServiceMgr
    ServiceMgr -->|Repository calls| PG
    ServiceMgr -->|Get/Set| Redis
    
    Celery -->|Task execution| ServiceMgr
    Beat -->|Enqueue tasks| Redis
    
    FastAPI -.->|sync (manual)| eBay
    FastAPI -.->|sync (manual)| Shopify
    FastAPI -.->|ETL (scheduled)| Scryfall
    FastAPI -.->|ETL (scheduled)| MTGJson
    FastAPI -.->|ETL (scheduled)| MTGStock
    
    style Client fill:#e1f5ff
    style Network fill:#fff3e0
    style Backend fill:#f3e5f5
    style Data fill:#e8f5e9
    style External fill:#fce4ec
    style Jobs fill:#ede7f6
```

**Legend:**
- Solid arrows: Request/response paths
- Dotted arrows: Integration/sync paths
- Subgraphs: Logical system zones

---

## Data Residency Map

### PostgreSQL (Primary Data Store)

| Table/Schema | Purpose | Key Columns | Ownership |
|---|---|---|---|
| `card_catalog.*` | Card definitions (normalized) | id, name, scryfall_id | Scryfall pipeline |
| `user_collections.*` | User card collections | user_id, card_id, quantity | User APIs |
| `pricing.price_observations` | TimescaleDB hypertable for price history | time, card_id, source, price | MTGStock/MTGJson pipelines |
| `pricing.price_staging` | Staging table for bulk price loads | — | MTGStock/MTGJson pipelines |
| `auth.sessions` | User session tokens | user_id, session_id, expires_at | Auth middleware |
| `card_embeddings.*` | pgvector embeddings for similarity search | card_id, embedding | Scryfall enrichment |
| `integrations.ebay_user_scopes` | eBay OAuth scopes per user | user_id, scope, grant_type | eBay integration |
| `integrations.ebay_listings` | Cached eBay listing data | user_id, listing_id, title, price | eBay sync |
| `ops.ingestion_runs` | ETL pipeline execution tracking | run_id, pipeline, status, started_at | Pipeline execution |

### Redis (Cache & Queue)

| Key Pattern | Purpose | TTL | Size Estimate |
|---|---|---|---|
| `session:{session_id}` | Active user session | 30 days | ~1KB per session |
| `user:{user_id}:profile` | Cached user profile data | 1 hour | ~500B per user |
| `celery:queue:*` | Celery task queues | — | Variable (drains as tasks process) |
| `celery:result:{task_id}` | Task execution results | 1 hour | ~1-100KB per task |
| `cache:card:{card_id}` | Card detail cache | 7 days | ~2-5KB per card |
| `cache:prices:{card_id}` | Cached price data | 1 hour | ~500B per card |

### File System

| Location | Purpose | Ownership | Notes |
|---|---|---|---|
| `/data/postgres/` | PostgreSQL data files (Docker bind mount) | PostgreSQL | Persistent storage |
| `/data/automana_data/mtgstocks/raw/prints/` | Raw MTGStock CSV files | MTGStock pipeline | Downloaded, not committed to git |
| `/data/mtgjson/` | MTGJson bulk data cache | MTGJson pipeline | Downloaded, cached for processing |
| `src/frontend/dist/` | Built React app (static assets) | Frontend build | Served by nginx |
| `logs/` | Application logs (if file-based) | Celery/FastAPI | Usually aggregated to stdout (Docker) |

### External Services

| Service | Data | Rate Limits | Auth |
|---|---|---|---|
| **eBay API** | User listings, orders, inventory | 10,000 calls/day per app | OAuth 2.0 tokens (stored encrypted in DB) |
| **Shopify API** | Products, orders | 2 requests/second per store | API key + password (in env vars) |
| **Scryfall** | Complete card database | 50ms between requests | Rate limit headers (no auth) |
| **MTGJson** | All Magic card data | 1 request/day | None |
| **MTGStock** | Current market prices | 1 request/day | API key (in env var) |

---

## Cross-System Data Flows

[TO BE COMPLETED IN TASK 4]

---

## Critical Paths & Dependencies

[TO BE COMPLETED IN TASK 5]

---

## Documentation Navigator

[TO BE COMPLETED IN TASK 6]
