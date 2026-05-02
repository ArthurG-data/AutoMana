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

[TO BE COMPLETED IN TASK 3]

---

## Cross-System Data Flows

[TO BE COMPLETED IN TASK 4]

---

## Critical Paths & Dependencies

[TO BE COMPLETED IN TASK 5]

---

## Documentation Navigator

[TO BE COMPLETED IN TASK 6]
