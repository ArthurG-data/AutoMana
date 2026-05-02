# MTGStocks ETL Pipeline Guide

## Overview

The MTGStocks pipeline ingests Magic: The Gathering price data scraped from MTGStocks marketplace and lands it in the AutoMana `pricing` schema. Unlike Scryfall (card metadata) and MTGJson (wholesale indices), MTGStocks provides **retail market prices** with condition/finish granularity.

**Key complexity:** MTGStocks uses proprietary `print_id` identifiers that must first be **resolved to `card_version_id`** before prices can join the rest of the catalog.

**Key characteristics:**
- **Four-stage pipeline:** Raw → Staging (with resolution) → Retry rejects → Observation
- **Identifier resolution:** `print_id` → `card_version_id` via Scryfall migration table
- **Reject recovery:** Previously-rejected rows are re-attempted with fresh resolution data
- **Fact table:** TimescaleDB hypertable with 7-day chunks, auto-compression after 180 days
- **Idempotent:** Safe to re-run via `ON CONFLICT DO NOTHING` at staging layer

---

## Architecture Overview

### Data Flow Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│ MTGStocks Scraper Output (CSV/JSON)                                 │
│  - print_id (proprietary identifier)                                 │
│  - price_list, price_mid, price_high, price_low                    │
│  - condition (NM, LP, MP, HP)                                        │
│  - foil (true/false)                                                 │
│  - ts_date (timestamp)                                               │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────────────┐
        │ Celery Task: mtgStock_download_pipeline              │
        │ (Scheduled daily or manual trigger)                  │
        └─────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────────────┐
         │                    │                            │
         ▼                    ▼                            ▼
    ┌────────────┐      ┌────────────┐             ┌────────────┐
    │  Stage 1   │      │  Stage 2   │             │  Stage 3   │
    │Raw Landing │      │ Resolve +  │             │  Finalize  │
    │            │      │Reject Flow │             │            │
    └────────────┘      └────────────┘             └────────────┘
         │                    │                            │
         ├─ bulk_load         ├─ from_raw_to_staging    ├─ finish_run
         │                    ├─ retry_rejects          │
         │                    └─ from_staging_to_prices │
         │                                                 │
    pricing.raw_mtg_stock_price
         │
         ├──> pricing.stg_price_observation
         │    pricing.stg_price_observation_reject
         │
         ├──> (retry with fresh resolution data)
         │
         └──> pricing.price_observation (fact table)
              pricing.print_price_daily (rollup)
              pricing.print_price_latest (snapshot)
```

### Service Chain Definition

**File:** `src/automana/worker/tasks/pipelines.py` (lines 50-82)

```python
@shared_task(name="mtgStock_download_pipeline", bind=True)
def mtgStock_download_pipeline(self):
    set_task_id(self.request.id)
    run_key = f"mtgStock_All:{datetime.utcnow().date().isoformat()}"
    logger.info("Starting MTGStock download pipeline", extra={"run_key": run_key})
    
    wf = chain(
        # Stage 1: Create run record
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtg_stock_all",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        
        # Stage 2: Raw landing
        run_service.s("mtg_stock.data_staging.bulk_load",
                      root_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=2000,
                      market="tcg"),
        
        # Stage 3: Resolve + stage with reject handling
        run_service.s("mtg_stock.data_staging.from_raw_to_staging",
                      source_name="mtgstocks"),
        
        # Stage 4: Retry previously-rejected rows
        run_service.s("mtg_stock.data_staging.retry_rejects"),
        
        # Stage 5: Load facts
        run_service.s("mtg_stock.data_staging.from_staging_to_prices"),
        
        # Stage 6: Finish
        run_service.s("ops.pipeline_services.finish_run", status="success")
    )
    return wf.apply_async().id
```

---

## Pricing Data Model

### The Chain: Card → Product → Observation

```
┌──────────────────────────────────────────────────────────────┐
│ Platonic Card (e.g., "Lightning Bolt")                        │
│  card_catalog.unique_cards_ref                                │
│                                                                │
│  Fields: name, rules_text, type_line, mana_cost              │
│  Primary Key: unique_card_id (UUID)                           │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ Card Version (specific printing)                              │
│  card_catalog.card_version                                    │
│                                                                │
│  One per (set, collector_number, frame)                       │
│  Carries scryfall_id, art, border, language, etc.            │
│  Primary Key: card_version_id (UUID)                          │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ MTG Card Product (1-to-1 bridge)                              │
│  pricing.mtg_card_products                                    │
│                                                                │
│  Links card_version ↔ product_ref                             │
│  Ensures uniqueness: UNIQUE(card_version_id)                  │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ Game-agnostic Product                                         │
│  pricing.product_ref                                          │
│                                                                │
│  One product = one physical card (MTG, Pokémon, YGO, …)      │
│  Primary Key: product_id (UUID)                               │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ Source Product (Product × Marketplace)                        │
│  pricing.source_product                                       │
│                                                                │
│  e.g., "Lightning Bolt (Alpha)" on "TCGPlayer" in "NM foil"  │
│  Primary Key: source_product_id (BIGSERIAL)                   │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ Price Observation (Fact Table)                                │
│  pricing.price_observation (TimescaleDB hypertable)           │
│                                                                │
│  Grain: (ts_date, source_product_id, data_provider)          │
│  Metrics: list_low_cents, list_avg_cents, sold_avg_cents     │
│  Partitioned by ts_date (7-day chunks)                        │
└──────────────────────────────────────────────────────────────┘
```

### Dimension Reference Tables

| Dimension | Table | Role | Default |
|-----------|-------|------|---------|
| **Finish** | `pricing.card_finish` | Card variant (foil/nonfoil) | `NONFOIL` |
| **Condition** | `pricing.card_condition` | Physical condition | `NM` (Near Mint) |
| **Language** | `card_catalog.language_ref` | Card language | `en` |
| **Source** | `pricing.price_source` | Marketplace (TCGPlayer, etc.) | — |
| **Data Provider** | `pricing.data_provider` | Data source (MTGStocks, MTGJson) | — |
| **Transaction Type** | `pricing.transaction_type` | Buy/sell | `sell` (listing prices) |
| **Currency** | `pricing.currency_ref` | Price currency | `USD` |

### Fact Table: `price_observation`

One row = **(date, source_product, transaction, foil, condition, language, provider)**

| Column | Type | Role |
|--------|------|------|
| `ts_date` | DATE | TimescaleDB partitioning key |
| `source_product_id` | BIGINT | FK to source_product |
| `price_type_id` | INT | Transaction type (sell, etc.) |
| `finish_id` | INT | Foil/nonfoil |
| `condition_id` | INT | NM, LP, MP, HP |
| `language_id` | INT | Card language |
| `data_provider_id` | INT | mtgstocks, mtgjson, etc. |
| `list_low_cents` | INT | Lowest listing price (cents) |
| `list_avg_cents` | INT | Average listing price |
| `sold_avg_cents` | INT | Average sold price (if available) |
| `list_count` | INT | Number of listings |
| `sold_count` | INT | Number of sales records |

**Primary Key:** `(ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)`

**Compression:** Auto-compress chunks > 180 days old (slow path)

---

## Stage 1: Raw Landing

### 1.1 Bulk Load

**File:** `src/automana/core/services/app_integration/mtgstock/data_loader.py`

```python
@ServiceRegistry.register("mtg_stock.data_staging.bulk_load",
                         db_repositories=["pricing"],
                         storage_services=["mtgstock"])
async def bulk_load(
    pricing_repository: PricingRepository,
    storage_service: StorageService,
    ingestion_run_id: int = None,
    root_folder: str = "/data/automana_data/mtgstocks/raw/prints/",
    batch_size: int = 2000,
    market: str = "tcg"
) -> Dict[str, int]:
    """
    Bulk-load CSV/JSON files from MTGStocks scraper into raw table.
    
    Process:
    1. Scan root_folder for market-specific files (e.g., tcg_*.csv)
    2. Read and parse each file
    3. COPY batch-by-batch to pricing.raw_mtg_stock_price
    4. Return count of rows inserted
    
    Args:
        root_folder: Path where scraper writes files
        batch_size: COPY batch size (2000 = good throughput)
        market: Market identifier (tcg, cardkingdom, etc.)
        ingestion_run_id: Run identifier for tracking
        
    Returns:
        {"raw_rows_inserted": int}
    
    Schema of pricing.raw_mtg_stock_price:
        id (SERIAL PK)
        print_id (VARCHAR)                      ← MTGStocks identifier
        market (VARCHAR)                        ← tcg, cardkingdom, etc.
        price_list (NUMERIC)                    ← List price (currency)
        price_mid (NUMERIC)
        price_high (NUMERIC)
        price_low (NUMERIC)
        foil (BOOLEAN)
        condition (VARCHAR)                     ← NM, LP, MP, HP
        language (VARCHAR)                      ← en, ja, de, etc.
        ts_date (DATE)
        inserted_at (TIMESTAMP)
    """
    
    total_inserted = 0
    
    # List all scraper output files
    files = await storage_service.list_files(f"{root_folder}/{market}_*.csv")
    
    for file_path in files:
        logger.info("Loading MTGStocks file", extra={
            "file": file_path,
            "ingestion_run_id": ingestion_run_id
        })
        
        batch = []
        rows_in_file = 0
        
        async with storage_service.open_stream(file_path, "r") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                batch.append({
                    "print_id": row["print_id"],
                    "market": market,
                    "price_list": float(row["price_list"]),
                    "price_mid": float(row.get("price_mid", 0)),
                    "price_high": float(row.get("price_high", 0)),
                    "price_low": float(row.get("price_low", 0)),
                    "foil": row.get("foil", "false").lower() == "true",
                    "condition": row.get("condition", "NM"),
                    "language": row.get("language", "en"),
                    "ts_date": datetime.strptime(row["ts_date"], "%Y-%m-%d").date()
                })
                
                rows_in_file += 1
                
                if len(batch) >= batch_size:
                    # Bulk COPY
                    await pricing_repository.bulk_insert_raw_mtgstock(batch)
                    total_inserted += len(batch)
                    batch = []
            
            # Final batch
            if batch:
                await pricing_repository.bulk_insert_raw_mtgstock(batch)
                total_inserted += len(batch)
        
        logger.info("File loaded", extra={
            "file": file_path,
            "rows": rows_in_file,
            "ingestion_run_id": ingestion_run_id
        })
    
    logger.info("Raw landing completed", extra={
        "total_rows": total_inserted,
        "ingestion_run_id": ingestion_run_id
    })
    
    return {"raw_rows_inserted": total_inserted}
```

---

## Stage 2: Resolve & Stage with Reject Handling

### 2.1 Raw → Staging with Resolution

**File:** `src/automana/core/services/app_integration/mtgstock/pipeline.py`

The critical step: **map `print_id` to `card_version_id`**.

```python
@ServiceRegistry.register("mtg_stock.data_staging.from_raw_to_staging",
                         db_repositories=["pricing", "card_catalog"])
async def from_raw_to_staging(
    pricing_repository: PricingRepository,
    card_catalog_repo: CardCatalogRepository,
    ingestion_run_id: int = None,
    source_name: str = "mtgstocks"
) -> Dict[str, int]:
    """
    Resolve print_id to card_version_id and stage price rows.
    
    Process:
    1. Read rows from pricing.raw_mtg_stock_price
    2. For each row:
       a. Look up card_version_id via:
          - Direct: mtgstocks_external_id (if stored)
          - Resolution: card_catalog.scryfall_migration (old IDs)
          - Fallback: Fuzzy match by name (last resort, marked as suspect)
       b. If resolved → insert to stg_price_observation
       c. If NOT resolved → insert to stg_price_observation_reject
    3. Call stored procedure pricing.load_staging_prices_batched()
    
    Returns:
        {
            "staged": int,              # Rows in staging table
            "rejected": int,            # Rows in reject table
            "resolved_pct": float       # Percentage successfully resolved
        }
    
    Note:
        The stored procedure handles:
        - card_version_id lookup from raw.print_id
        - Market normalization (tcg → TCGPlayer source_id)
        - Dimension lookups (finish, condition, language)
        - ON CONFLICT DO NOTHING for idempotency
        - Error classification (reason_code)
    """
    
    async with track_step(pricing_repository, ingestion_run_id, "from_raw_to_staging",
                         error_code="resolution_failed"):
        
        # Call stored procedure
        result = await pricing_repository.load_staging_prices_batched(
            source_name=source_name,
            run_id=ingestion_run_id
        )
    
    staged = result.get("staged", 0)
    rejected = result.get("rejected", 0)
    total = staged + rejected
    resolved_pct = (staged / total * 100) if total > 0 else 0
    
    logger.info("Raw to staging completed", extra={
        "staged": staged,
        "rejected": rejected,
        "resolved_pct": resolved_pct,
        "ingestion_run_id": ingestion_run_id
    })
    
    return {
        "staged": staged,
        "rejected": rejected,
        "resolved_pct": resolved_pct
    }
```

### 2.2 Stored Procedure: `load_staging_prices_batched`

**File:** `src/automana/database/SQL/schemas/06_prices.sql`

```sql
CREATE OR REPLACE FUNCTION pricing.load_staging_prices_batched(
    p_source_name TEXT,
    p_run_id INT DEFAULT NULL
)
RETURNS TABLE(staged INT, rejected INT) AS $$
DECLARE
    v_source_id INT;
    v_rows_processed INT := 0;
    v_rows_staged INT := 0;
    v_rows_rejected INT := 0;
BEGIN
    -- Get source_id from source name
    SELECT id INTO v_source_id
    FROM pricing.price_source
    WHERE code = p_source_name;
    
    IF v_source_id IS NULL THEN
        RAISE EXCEPTION 'Unknown source: %', p_source_name;
    END IF;
    
    -- Insert from raw to staging (with resolution)
    INSERT INTO pricing.stg_price_observation (
        card_version_id,
        source_id,
        price_type_id,
        finish_id,
        condition_id,
        language_id,
        data_provider_id,
        list_low_cents,
        list_avg_cents,
        sold_avg_cents,
        list_count,
        sold_count,
        ts_date
    )
    SELECT
        COALESCE(
            -- Try direct external_id match
            (SELECT cv.id FROM card_catalog.card_version cv
             WHERE cv.external_id = CONCAT('mtgstocks_', r.print_id)
             LIMIT 1),
            
            -- Try Scryfall migration (old ID resolution)
            (SELECT cv.id FROM card_catalog.card_version cv
             JOIN card_catalog.scryfall_migration m ON m.new_scryfall_id = cv.scryfall_id
             WHERE CONCAT('scryfall_', m.old_scryfall_id) = CONCAT('scryfall_', r.print_id)
             LIMIT 1),
            
            -- Fuzzy match by name (last resort)
            (SELECT cv.id FROM card_catalog.card_version cv
             JOIN card_catalog.unique_cards_ref c ON c.id = cv.unique_card_id
             WHERE c.name ILIKE r.name
             LIMIT 1)
        ) AS card_version_id,
        v_source_id,
        (SELECT id FROM pricing.transaction_type WHERE code = 'sell'),
        CASE WHEN r.foil THEN (SELECT id FROM pricing.card_finish WHERE code = 'FOIL')
             ELSE (SELECT id FROM pricing.card_finish WHERE code = 'NONFOIL') END,
        CASE WHEN r.condition IS NULL THEN (SELECT id FROM pricing.card_condition WHERE code = 'NM')
             ELSE (SELECT id FROM pricing.card_condition WHERE code = r.condition) END,
        (SELECT id FROM card_catalog.language_ref WHERE code = COALESCE(r.language, 'en')),
        (SELECT id FROM pricing.data_provider WHERE code = p_source_name),
        ROUND(r.price_low * 100)::INT,
        ROUND(r.price_mid * 100)::INT,
        NULL,  -- sold_avg not available from MTGStocks
        1,     -- list_count = 1 (one listing observed)
        NULL,  -- sold_count not available
        r.ts_date
    FROM pricing.raw_mtg_stock_price r
    WHERE r.market = p_source_name
    ON CONFLICT DO NOTHING
    
    GET DIAGNOSTICS v_rows_staged = ROW_COUNT;
    
    -- Rows that couldn't be resolved go to reject table
    INSERT INTO pricing.stg_price_observation_reject (
        raw_data,
        reason_code,
        ts_date
    )
    SELECT
        jsonb_build_object(
            'print_id', r.print_id,
            'price_list', r.price_list,
            'condition', r.condition,
            'foil', r.foil
        ),
        'NO_CARD_VERSION_MATCH',
        r.ts_date
    FROM pricing.raw_mtg_stock_price r
    WHERE r.market = p_source_name
    AND NOT EXISTS (
        SELECT 1 FROM pricing.stg_price_observation sp
        WHERE sp.ts_date = r.ts_date
        AND CAST(sp.raw_data->>'print_id' AS TEXT) = r.print_id
    )
    ON CONFLICT DO NOTHING;
    
    GET DIAGNOSTICS v_rows_rejected = ROW_COUNT;
    
    -- Delete from raw (cleanup)
    DELETE FROM pricing.raw_mtg_stock_price
    WHERE market = p_source_name;
    
    RETURN QUERY SELECT v_rows_staged, v_rows_rejected;
END;
$$ LANGUAGE plpgsql;
```

---

## Stage 3: Retry Rejects

### 3.1 Retry Rejects Service

**File:** `src/automana/core/services/app_integration/mtgstock/pipeline.py`

Rows in the reject table get a second chance with fresh resolution data (new migrations from Scryfall, etc.):

```python
@ServiceRegistry.register("mtg_stock.data_staging.retry_rejects",
                         db_repositories=["pricing"])
async def retry_rejects(
    pricing_repository: PricingRepository,
    ingestion_run_id: int = None
) -> Dict[str, int]:
    """
    Re-attempt resolution for previously-rejected rows.
    
    Rationale:
        Rows rejected in Stage 2 might resolve now if:
        - New card_catalog.scryfall_migration entries were added (Scryfall updates)
        - Previous resolution failure was transient
        - Fresh fuzzy matching gives different result
    
    Process:
    1. Read rows from pricing.stg_price_observation_reject
    2. Re-run resolution logic
    3. Rows that now resolve → move to stg_price_observation
    4. Rows that still reject → remain in reject table (logged for manual review)
    
    Returns:
        {
            "recovered": int,           # Rows moved from reject → staging
            "still_rejected": int       # Rows still unresolved
        }
    """
    
    async with track_step(pricing_repository, ingestion_run_id, "retry_rejects",
                         error_code="retry_failed"):
        
        # Call stored procedure
        result = await pricing_repository.resolve_price_rejects(
            run_id=ingestion_run_id
        )
    
    recovered = result.get("recovered", 0)
    still_rejected = result.get("still_rejected", 0)
    
    logger.info("Retry rejects completed", extra={
        "recovered": recovered,
        "still_rejected": still_rejected,
        "ingestion_run_id": ingestion_run_id
    })
    
    return {
        "recovered": recovered,
        "still_rejected": still_rejected
    }
```

### 3.2 Stored Procedure: `resolve_price_rejects`

```sql
CREATE OR REPLACE FUNCTION pricing.resolve_price_rejects(
    p_run_id INT DEFAULT NULL
)
RETURNS TABLE(recovered INT, still_rejected INT) AS $$
DECLARE
    v_recovered INT := 0;
BEGIN
    -- Try to resolve rejects using fresh resolution logic
    WITH resolved AS (
        SELECT
            (sr.raw_data->>'print_id')::TEXT AS print_id,
            COALESCE(
                -- Fresh migration lookup
                (SELECT cv.id FROM card_catalog.card_version cv
                 JOIN card_catalog.scryfall_migration m ON m.new_scryfall_id = cv.scryfall_id
                 WHERE CONCAT('scryfall_', m.old_scryfall_id) = 
                       CONCAT('scryfall_', sr.raw_data->>'print_id')
                 LIMIT 1),
                
                -- Fuzzy match
                (SELECT cv.id FROM card_catalog.card_version cv
                 WHERE cv.name ILIKE sr.raw_data->>'name'
                 LIMIT 1)
            ) AS card_version_id
        FROM pricing.stg_price_observation_reject sr
        WHERE sr.reason_code = 'NO_CARD_VERSION_MATCH'
        AND sr.resolved_at IS NULL
    )
    INSERT INTO pricing.stg_price_observation (
        card_version_id,
        source_id,
        price_type_id,
        finish_id,
        condition_id,
        language_id,
        data_provider_id,
        list_low_cents,
        list_avg_cents,
        ts_date
    )
    SELECT
        resolved.card_version_id,
        (SELECT id FROM pricing.price_source WHERE code = 'mtgstocks'),
        (SELECT id FROM pricing.transaction_type WHERE code = 'sell'),
        (SELECT id FROM pricing.card_finish WHERE code = 'NONFOIL'),
        (SELECT id FROM pricing.card_condition WHERE code = 'NM'),
        (SELECT id FROM card_catalog.language_ref WHERE code = 'en'),
        (SELECT id FROM pricing.data_provider WHERE code = 'mtgstocks'),
        (resolved.raw_data->>'price_low')::INT,
        (resolved.raw_data->>'price_mid')::INT,
        resolved.ts_date
    FROM resolved
    WHERE resolved.card_version_id IS NOT NULL
    ON CONFLICT DO NOTHING;
    
    GET DIAGNOSTICS v_recovered = ROW_COUNT;
    
    -- Mark recovered rows as resolved
    UPDATE pricing.stg_price_observation_reject
    SET resolved_at = NOW()
    WHERE reason_code = 'NO_CARD_VERSION_MATCH'
    AND resolved_at IS NULL
    AND (raw_data->>'print_id')::TEXT IN (
        SELECT print_id FROM resolved WHERE card_version_id IS NOT NULL
    );
    
    -- Count still-rejected
    SELECT COUNT(*) INTO v_still_rejected
    FROM pricing.stg_price_observation_reject
    WHERE reason_code = 'NO_CARD_VERSION_MATCH'
    AND resolved_at IS NULL;
    
    RETURN QUERY SELECT v_recovered, v_still_rejected;
END;
$$ LANGUAGE plpgsql;
```

---

## Stage 4: Load Facts

### 4.1 Staging → Observation

**File:** `src/automana/core/services/app_integration/mtgstock/pipeline.py`

```python
@ServiceRegistry.register("mtg_stock.data_staging.from_staging_to_prices",
                         db_repositories=["pricing"])
async def from_staging_to_prices(
    pricing_repository: PricingRepository,
    ingestion_run_id: int = None,
    staged: int = None,
    rejected: int = None,
    recovered: int = None
) -> Dict[str, int]:
    """
    Promote rows from staging to fact table (price_observation).
    
    Process:
    1. Call pricing.load_prices_from_staged_batched()
    2. This procedure:
       - Creates source_product if needed (card_version × source × condition × finish)
       - Inserts fact rows into price_observation
       - Handles TimescaleDB hypertable insertion (partitioned by ts_date)
    3. Delete staged rows on success
    
    Returns:
        {
            "price_observations_loaded": int,
            "source_products_created": int
        }
    """
    
    async with track_step(pricing_repository, ingestion_run_id, "from_staging_to_prices",
                         error_code="promotion_failed"):
        
        # Call stored procedure
        result = await pricing_repository.load_prices_from_staged_batched()
    
    observations_loaded = result.get("observations_loaded", 0)
    source_products_created = result.get("source_products_created", 0)
    
    logger.info("Staging to prices completed", extra={
        "observations_loaded": observations_loaded,
        "source_products_created": source_products_created,
        "total_staged": staged,
        "total_rejected": rejected,
        "recovered": recovered,
        "ingestion_run_id": ingestion_run_id
    })
    
    return {
        "price_observations_loaded": observations_loaded,
        "source_products_created": source_products_created
    }
```

### 4.2 Stored Procedure: `load_prices_from_staged_batched`

```sql
CREATE OR REPLACE FUNCTION pricing.load_prices_from_staged_batched()
RETURNS TABLE(
    observations_loaded INT,
    source_products_created INT
) AS $$
DECLARE
    v_obs_loaded INT := 0;
    v_sp_created INT := 0;
BEGIN
    -- Create missing source_product rows
    WITH missing_sp AS (
        SELECT DISTINCT
            sp.card_version_id,
            sp.source_id,
            sp.finish_id,
            sp.condition_id,
            sp.language_id
        FROM pricing.stg_price_observation sp
        WHERE NOT EXISTS (
            SELECT 1 FROM pricing.source_product spp
            WHERE spp.product_id = (
                SELECT pf.product_id FROM pricing.mtg_card_products pf
                WHERE pf.card_version_id = sp.card_version_id
            )
            AND spp.source_id = sp.source_id
            AND spp.finish_id = sp.finish_id
            AND spp.condition_id = sp.condition_id
            AND spp.language_id = sp.language_id
        )
    )
    INSERT INTO pricing.source_product (
        product_id,
        source_id,
        finish_id,
        condition_id,
        language_id
    )
    SELECT
        pf.product_id,
        missing_sp.source_id,
        missing_sp.finish_id,
        missing_sp.condition_id,
        missing_sp.language_id
    FROM missing_sp
    JOIN pricing.mtg_card_products pf ON pf.card_version_id = missing_sp.card_version_id
    ON CONFLICT DO NOTHING;
    
    GET DIAGNOSTICS v_sp_created = ROW_COUNT;
    
    -- Insert observations
    INSERT INTO pricing.price_observation (
        ts_date,
        source_product_id,
        price_type_id,
        finish_id,
        condition_id,
        language_id,
        data_provider_id,
        list_low_cents,
        list_avg_cents,
        sold_avg_cents,
        list_count,
        sold_count
    )
    SELECT
        sp.ts_date,
        spp.id,
        sp.price_type_id,
        sp.finish_id,
        sp.condition_id,
        sp.language_id,
        sp.data_provider_id,
        sp.list_low_cents,
        sp.list_avg_cents,
        sp.sold_avg_cents,
        sp.list_count,
        sp.sold_count
    FROM pricing.stg_price_observation sp
    JOIN pricing.mtg_card_products pf ON pf.card_version_id = sp.card_version_id
    JOIN pricing.source_product spp ON (
        spp.product_id = pf.product_id
        AND spp.source_id = sp.source_id
        AND spp.finish_id = sp.finish_id
        AND spp.condition_id = sp.condition_id
        AND spp.language_id = sp.language_id
    )
    ON CONFLICT (ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)
    DO UPDATE SET
        list_low_cents = EXCLUDED.list_low_cents,
        list_avg_cents = EXCLUDED.list_avg_cents,
        sold_avg_cents = EXCLUDED.sold_avg_cents,
        list_count = EXCLUDED.list_count,
        sold_count = EXCLUDED.sold_count;
    
    GET DIAGNOSTICS v_obs_loaded = ROW_COUNT;
    
    -- Delete staged rows
    DELETE FROM pricing.stg_price_observation;
    
    RETURN QUERY SELECT v_obs_loaded, v_sp_created;
END;
$$ LANGUAGE plpgsql;
```

---

## Performance Optimization

### Batch COPY

```python
async def bulk_insert_raw_mtgstock(self, batch: List[Dict]):
    """Use COPY for 50x faster insertion than INSERT."""
    
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=RAW_FIELDS)
    writer.writeheader()
    for record in batch:
        writer.writerow(record)
    
    csv_buffer.seek(0)
    await self.connection.copy_to_table(
        "pricing.raw_mtg_stock_price",
        source=csv_buffer,
        format='csv',
        header=True
    )
```

### Parallel Resolution

Resolution via scryfall_migration is fast because:
- Migration table is tiny (~5K rows, indexed)
- INNER JOIN on indexed scryfall_id
- Plan: ~1ms per row

### TimescaleDB Hypertable

```sql
-- Automatic partitioning by ts_date
SELECT create_hypertable('pricing.price_observation', 'ts_date',
    if_not_exists => TRUE);

-- Auto-compression: chunks > 180 days
ALTER TABLE pricing.price_observation SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'source_product_id,price_type_id,finish_id',
    timescaledb.compress_orderby = 'ts_date DESC'
);

SELECT add_compression_policy('pricing.price_observation',
    INTERVAL '180 days');
```

---

## Error Handling

### Reject Tracking

Rows that fail resolution are captured in `stg_price_observation_reject`:

```sql
CREATE TABLE pricing.stg_price_observation_reject (
    id SERIAL PRIMARY KEY,
    raw_data JSONB,                -- Original row values
    reason_code VARCHAR(50),       -- NO_CARD_VERSION_MATCH, etc.
    ts_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,         -- Set when recovered
    notes TEXT
);
```

### Metrics

```python
class MTGStockMetrics:
    pipeline_runs_total = Counter("mtgstock_pipeline_runs_total")
    raw_rows_loaded = Gauge("mtgstock_raw_rows_loaded")
    rows_staged = Gauge("mtgstock_rows_staged")
    rows_rejected = Gauge("mtgstock_rows_rejected")
    rows_recovered = Gauge("mtgstock_rows_recovered")
    price_observations_loaded = Gauge("mtgstock_price_observations_loaded")
    resolution_success_rate = Gauge("mtgstock_resolution_success_rate")
```

---

## Monitoring & Logging

### Structured Logging

```python
logger.info("mtgstock_pipeline_completed", extra={
    "ingestion_run_id": 12345,
    "run_key": "mtgStock_All:2026-04-28",
    "raw_rows": 50000,
    "staged": 49500,
    "rejected": 500,
    "recovered": 100,
    "still_rejected": 400,
    "observations_loaded": 49600,
    "resolution_success_pct": 99.2,
    "duration_seconds": 145.5
})
```

---

## Related Documentation

- **MTGSTOCK_PIPELINE.md** (existing): Full pipeline documentation
- **MTGSTOCK_REJECT_ANALYSIS.md**: Detailed reject analysis and recovery strategies
- **PIPELINE_TECHNICAL_DEBT.md**: Known issues (ID resolution edge cases)
- **DESIGN_PATTERNS.md**: `track_step()`, service registry patterns
