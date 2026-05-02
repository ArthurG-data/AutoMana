# Database Schema Design

This document describes the complete schema structure, normalization strategy, indexing approach, constraints, and special PostgreSQL/TimescaleDB features used in AutoMana.

**Schema Files:** [`src/automana/database/SQL/schemas/`](../../../src/automana/database/SQL/schemas/)

---

## Table of Contents

1. [Schema Philosophy](#schema-philosophy)
2. [Core Schemas & Tables](#core-schemas--tables)
3. [Entity-Relationship Diagram](#entity-relationship-diagram)
4. [Database Roles & Access Control](#database-roles--access-control)
5. [Indexing Strategy](#indexing-strategy)
6. [Constraints & Triggers](#constraints--triggers)
7. [TimescaleDB Hypertables](#timescaledb-hypertables)
8. [Backup & Recovery](#backup--recovery)

---

## Schema Philosophy

### Normalization

AutoMana uses a **mixed normalization strategy**:

- **3NF for reference tables**: `card_catalog.*_ref`, `pricing.*_ref` tables (artists, rarities, colors, etc.) are fully normalized to reduce redundancy and ensure consistency.
- **Denormalization for performance**: The `card_version` table includes columns like `card_name`, `set_code`, `rarity_name` (duplicated from reference tables) to optimize query performance for card searches and aggregations. This is acceptable because these denormalized fields are updated only during ETL pipelines (immutable after initial load).
- **Time-series normalization**: The `pricing.*` schema uses a multi-tier structure (observation → daily → weekly) to balance storage, query speed, and historical granularity. Older data is automatically compressed.

### PostgreSQL Features Used

- **UUID Primary Keys**: Most tables use UUID for portability and to avoid sequence coordination across services.
- **SERIAL/SMALLSERIAL for Reference Lookups**: Dimension tables (rarities, colors, finishes) use small SERIAL IDs to reduce storage and join overhead.
- **Foreign Key Constraints**: Enforced at the database level to prevent orphaned rows.
- **CHECK Constraints**: Used extensively to validate prices (non-negative), conditions, and other domain rules.
- **Triggers**: Log changes (e.g., user disable, role assignment) to audit tables.
- **Views**: Flattened views (e.g., `v_card_name_suggest`, `v_active_sessions`) join normalized tables for efficient queries.
- **GUC (Grand Unified Configuration)**: Application layer sets session variables (e.g., `app.current_user_id`) that triggers can read via `current_setting()`.

### TimescaleDB Extensions

- **Hypertables**: Automatic time-based partitioning for the `price_observation`, `print_price_daily`, and `print_price_weekly` tables.
- **Compression**: Time-range and column-wise compression with automatic policies for data older than 30–180 days.
- **Chunk Management**: 7-day and 28-day chunk intervals balance query performance and storage efficiency.

---

## Core Schemas & Tables

### Schema: `card_catalog`

Manages Magic: The Gathering card definitions and metadata.

**File:** [`02_card_schema.sql`](../../../src/automana/database/SQL/schemas/02_card_schema.sql)

#### `unique_cards_ref`
Canonical card identity (one row per unique card name/properties).

| Column | Type | Constraints | Notes |
|--------|------|-----------|-------|
| `unique_card_id` | UUID | PK, DEFAULT uuid_generate_v4() | Global card identity |
| `card_name` | TEXT | NOT NULL, UNIQUE | Card name |
| `cmc` | INT | | Converted mana cost |
| `mana_cost` | VARCHAR(50) | | Mana cost string (e.g., `{1}{U}{U}`) |
| `reserved` | BOOL | DEFAULT false | Reserved List status |
| `other_face_id` | UUID | FK to self | For modal/double-faced cards |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | |

**Indexes:**
- `UNIQUE(card_name)` — ensures card identity uniqueness
- Natural clustered on PK

#### `card_version`
One row per printable card (unique card + set + collector number combination).

| Column | Type | Constraints | Notes |
|--------|------|-----------|-------|
| `card_version_id` | UUID | PK | Unique print identifier |
| `unique_card_id` | UUID | FK to `unique_cards_ref` | Card identity |
| `set_id` | UUID | FK to `sets` | Which set this print appears in |
| `collector_number` | VARCHAR(10) | | Number within the set (e.g., `42a`) |
| `card_name` | TEXT | **DENORMALIZED** | Query optimization |
| `set_code` | VARCHAR(5) | **DENORMALIZED** | Query optimization (e.g., `MID`) |
| `rarity_name` | VARCHAR(20) | **DENORMALIZED** | Query optimization |
| `rarity_id` | SMALLINT | FK to `rarities_ref` | Rarity dimension |
| `oracle_text` | TEXT | | Card rules text |
| `flavor_text` | TEXT | | Flavor text |
| `illustration_artist` | UUID | FK to `artists_ref` | Artist of this specific print |
| `lang` | VARCHAR(5) | | Language code (e.g., `en`, `de`) |
| `released_at` | DATE | | Official release date |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | |

**Indexes:**
- `idx_card_version_set_collector` on `(set_id, collector_number)` — fast set+collector lookups
- `idx_card_version_scryfall_id` on scryfall identifier (external key)
- `idx_card_version_unique_id` on `unique_card_id` — join to card names
- `idx_card_version_rarity` on `rarity_id` — filter by rarity

**Why Denormalization?**
ETL pipelines produce thousands of card_version rows. Embedding `card_name`, `set_code`, and `rarity_name` avoids the JOIN overhead on every search. These fields are immutable after initial load.

#### `artists_ref`
Canonical artist identities.

| Column | Type | Constraints | Notes |
|--------|------|-----------|-------|
| `artist_id` | UUID | PK | |
| `artist_name` | VARCHAR(255) | NOT NULL, UNIQUE | Full credit (supports collabs like "Avon / McKinnon") |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | |

**Sentinel Row:**
- **ID:** `00000000-0000-0000-0000-000000000001`
- **Name:** `Unknown Artist`
- **Purpose:** Placeholder for Scryfall cards with scrubbed metadata (basics, tokens). Keeps referential integrity intact instead of rejecting ~38k rows per import.

**Indexes:**
- `idx_artists_name` on `artist_name` — text search

#### `card_types`, `card_keyword`, `color_produced`
M2M (many-to-many) reference tables for multi-valued attributes.

| Table | Columns | Purpose |
|-------|---------|---------|
| `card_types` | `(unique_card_id, type_name)` PK | Type + subtype (e.g., "Creature", "Artifact Land"). Category enum: type / subtype / supertype |
| `card_keyword` | `(unique_card_id, keyword_id)` PK | Keywords (e.g., "Flying", "Lifelink") |
| `color_produced` | `(unique_card_id, color_id)` PK | Colors this card produces (mana symbols) |

#### Reference Lookup Tables
Small dimension tables for normalized fields:

| Table | Columns | Values |
|-------|---------|--------|
| `rarities_ref` | `rarity_id` (SERIAL), `rarity_name` (UNIQUE) | Common, Uncommon, Rare, Mythic, Special |
| `colors_ref` | `color_id` (SERIAL), `color_name` (UNIQUE) | W, U, B, R, G, C (colorless) |
| `frames_ref` | `frame_id` (SERIAL), `frame_year` (UNIQUE) | 1997, 2003, 2015, Future, etc. |
| `layouts_ref` | `layout_id` (SERIAL), `layout_name` (UNIQUE) | Normal, Modal, Double-Faced, Split, etc. |
| `keywords_ref` | `keyword_id` (SERIAL), `keyword_name` (UNIQUE) | Flying, Haste, Lifelink, etc. |
| `sets` | `set_id` (UUID), `set_code` (VARCHAR), `set_name` (TEXT), `released_at` (DATE) | MTG set metadata (linked from Scryfall) |

---

### Schema: `pricing`

High-volume time-series pricing data with multi-tier storage and compression.

**File:** [`06_prices.sql`](../../../src/automana/database/SQL/schemas/06_prices.sql)

#### Dimension Tables (Reference)

| Table | Purpose |
|-------|---------|
| `currency_ref` | ISO currency codes (USD, EUR, GBP, JPY, CAD) |
| `price_source` | Markets/marketplaces (tcgplayer, cardkingdom, ebay, mtgstocks, etc.) |
| `data_provider` | Data source type (mtgstocks scrape, mtgjson bulk, scryfall api) |
| `price_metric` | Metric types (low, avg, market, etc.) |
| `card_finished` | Card finishes (NONFOIL, FOIL, ETCHED, SURGE_FOIL, RIPPLE_FOIL, RAINBOW_FOIL) |
| `card_condition` | Condition codes (NM, LP, MP, HP, DMG, SP) |
| `transaction_type` | sell vs. buy |
| `product_ref` | Product identity (maps to card_version via mtg_card_products) |

#### ETL Staging Tables

Used during data ingestion:

- `stg_price_observation_reject` — rejected rows from staging (bad references, constraint violations)
- `stg_price_obs_date_spid_foil_idx` — partition index for reject resolution

#### Tier 1: `price_observation` (TimescaleDB Hypertable)

**Raw price data from all sources.**

| Column | Type | Constraints | Notes |
|--------|------|-----------|-------|
| `ts_date` | DATE | NOT NULL, PK component | Observation date (partitioned by range) |
| `source_product_id` | BIGINT | FK, PK component | Product + marketplace ID |
| `price_type_id` | INTEGER | FK, PK component | sell or buy |
| `finish_id` | SMALLINT | FK, PK component, DEFAULT | Card finish (FOIL, NONFOIL, etc.) |
| `condition_id` | SMALLINT | FK, PK component, DEFAULT | Card condition |
| `language_id` | SMALLINT | FK, PK component, DEFAULT | Card language |
| `data_provider_id` | SMALLINT | FK, PK component | mtgstocks, mtgjson, scryfall |
| `list_low_cents` | INTEGER | CHECK ≥ 0 | Lowest asking price |
| `list_avg_cents` | INTEGER | CHECK ≥ 0 | Average asking price |
| `sold_avg_cents` | INTEGER | CHECK ≥ 0 | Average sold price |
| `list_count` | INTEGER | | Number of listings |
| `sold_count` | INTEGER | | Number of transactions |
| `scraped_at` | TIMESTAMPTZ | DEFAULT now() | When data was collected |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | |

**Hypertable Config:**
- **Partitioning:** by_range on `ts_date` (daily chunks)
- **Chunk interval:** 7 days
- **Compression:** Column-wise (timescaledb.compress) on chunks > 180 days old
- **Segmentby:** `source_product_id, price_type_id, finish_id` (grouping for better compression)
- **Orderby:** `ts_date DESC` (frequent range queries on recent dates)

**Indexes:**
- `idx_price_date` on `(source_product_id, ts_date DESC)` — recent prices for a product

**Typical row volume:** ~500M–1B rows (compressed after 180 days)

#### Tier 2: `print_price_daily` (TimescaleDB Hypertable)

**Daily aggregate (one row per card + source + dimension combination).**

Populated by `pricing.refresh_daily_prices()` from Tier 1. Used for charts and historical trends.

| Column | Type | Notes |
|--------|------|-------|
| `price_date` | DATE | PK component |
| `card_version_id` | UUID | PK component, FK to card_catalog |
| `source_id` | SMALLINT | PK component |
| `transaction_type_id` | INTEGER | PK component |
| `finish_id` | SMALLINT | PK component |
| `condition_id` | SMALLINT | PK component |
| `language_id` | SMALLINT | PK component |
| `list_low_cents` | INTEGER | MIN(Tier 1 list_low) |
| `list_avg_cents` | INTEGER | AVG(Tier 1 list_avg) |
| `sold_avg_cents` | INTEGER | AVG(Tier 1 sold_avg) |
| `n_providers` | SMALLINT | COUNT(DISTINCT provider) |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Hypertable Config:**
- **Partitioning:** by_range on `price_date` (7-day chunks)
- **Compression:** Column-wise on chunks > 30 days old
- **Typical row volume:** ~10M–100M rows

#### Tier 3: `print_price_weekly` (TimescaleDB Hypertable)

**Weekly aggregate (one row per card + source + dimension for each Monday).**

Populated by `pricing.archive_to_weekly()` from Tier 2 for data > 5 years old. Reduces storage footprint while preserving trend visibility.

| Column | Type | Notes |
|--------|------|-------|
| `price_week` | DATE | PK component, Monday of ISO week |
| `card_version_id` | UUID | PK component |
| `source_id` | SMALLINT | PK component |
| `transaction_type_id` | INTEGER | PK component |
| `finish_id` | SMALLINT | PK component |
| `condition_id` | SMALLINT | PK component |
| `language_id` | SMALLINT | PK component |
| `list_low_cents` | INTEGER | MIN across week |
| `list_avg_cents` | INTEGER | AVG across week |
| `sold_avg_cents` | INTEGER | AVG across week |
| `n_days` | SMALLINT | Days with data (1–7) |
| `n_providers` | SMALLINT | Distinct providers in week |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Hypertable Config:**
- **Partitioning:** by_range on `price_week` (28-day chunks)
- **Compression:** Column-wise on chunks > 7 days old
- **Typical row volume:** ~1M–10M rows (heavily compressed)

#### `print_price_latest`

**Current price snapshot (non-hypertable regular table).**

One row per (card + source + dimensions), updated by `pricing.refresh_daily_prices()`. Enables sub-millisecond "current price" lookups.

| Column | Type | Notes |
|--------|------|-------|
| `card_version_id` | UUID | PK component |
| `source_id` | SMALLINT | PK component |
| `transaction_type_id` | INTEGER | PK component |
| `finish_id` | SMALLINT | PK component |
| `condition_id` | SMALLINT | PK component |
| `language_id` | SMALLINT | PK component |
| `price_date` | DATE | Latest observation date |
| `list_low_cents` | INTEGER | Current low ask |
| `list_avg_cents` | INTEGER | Current avg ask |
| `sold_avg_cents` | INTEGER | Current avg sell |
| `n_providers` | SMALLINT | Providers in latest batch |
| `updated_at` | TIMESTAMPTZ | |

**Indexes:**
- PK: `(card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)`
- `idx_ppl_card_source` on `(card_version_id, source_id)` — fast card+source lookups

#### `tier_watermark`

**Tracks last successfully processed date per tier.**

Used by `refresh_daily_prices()` and `archive_to_weekly()` to resume from the correct checkpoint after restart.

| Column | Type | Notes |
|--------|------|-------|
| `tier_name` | TEXT | PK ('daily', 'weekly') |
| `last_processed_date` | DATE | Last date processed |
| `updated_at` | TIMESTAMPTZ | |

---

### Schema: `user_management`

User authentication, sessions, roles, permissions, and audit logs.

**File:** [`03_users.sql`](../../../src/automana/database/SQL/schemas/03_users.sql)

#### `users`
User accounts (application users, not database roles).

| Column | Type | Constraints | Notes |
|--------|------|-----------|-------|
| `unique_id` | UUID | PK | User identity |
| `username` | TEXT | NOT NULL, UNIQUE | Login name |
| `email` | VARCHAR(50) | NOT NULL, UNIQUE | Email address |
| `fullname` | VARCHAR(50) | | Display name |
| `hashed_password` | TEXT | | bcrypt hash (never plaintext) |
| `disabled` | BOOL | DEFAULT false | Soft-disable flag |
| `deleted_at` | TIMESTAMPTZ | | Soft-delete sentinel (NULL = active) |
| `changed_by` | UUID | FK to self | Last person to modify this user |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | |

#### `sessions`
Active user sessions (auth tokens).

| Column | Type | Constraints | Notes |
|--------|------|-----------|-------|
| `id` | UUID | PK | Session ID |
| `user_id` | UUID | FK to `users` | Session owner |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | Session start |
| `expires_at` | TIMESTAMPTZ | NOT NULL | Expiration deadline |
| `ip_address` | VARCHAR(45) | | IPv4 or IPv6 |
| `user_agent` | TEXT | | Browser/client identifier |
| `device_id` | UUID | UNIQUE | Device fingerprint |
| `active` | BOOL | DEFAULT true | Can be revoked |

#### `refresh_tokens`
Token rotation for OAuth/JWT workflows.

| Column | Type | Constraints | Notes |
|--------|------|-----------|-------|
| `token_id` | UUID | PK | Token identity |
| `session_id` | UUID | FK to `sessions` | Associated session |
| `refresh_token` | TEXT | NOT NULL | Opaque token string |
| `refresh_token_expires_at` | TIMESTAMPTZ | NOT NULL | Expiration deadline |
| `used` | BOOL | DEFAULT false | Token already rotated |
| `revoked` | BOOL | DEFAULT false | Explicitly revoked |

#### Role-Based Access Control (RBAC)

**`roles`** — Application roles (not database roles).

| Column | Type |
|--------|------|
| `unique_id` | UUID PK |
| `role` | TEXT UNIQUE |
| `description` | TEXT |
| `created_at` | TIMESTAMPTZ |

**`user_roles`** — User-to-role assignment.

| Column | Type | Notes |
|--------|------|-------|
| `user_role_id` | SERIAL PK | |
| `user_id` | UUID FK | |
| `role_id` | UUID FK | |
| `assigned_at` | TIMESTAMPTZ | When assigned |
| `expires_at` | TIMESTAMPTZ | Optional role expiration |
| `effective_from` | TIMESTAMPTZ | When role becomes active |

**`permissions`** — Application permissions.

| Column | Type |
|--------|------|
| `permission_id` | UUID PK |
| `permission_name` | VARCHAR(50) UNIQUE |
| `description` | TEXT |

**`role_permissions`** — Role-to-permission assignment.

| Columns | Notes |
|---------|-------|
| `role_id`, `permission_id` | Composite PK |

#### Audit & Views

**`session_audit_logs`** — Session lifecycle events.
**`user_audit_logs`** — User account changes.
**`user_role_audit_logs`** — Role assignments and removals.

**Views:**
- `v_active_sessions` — currently valid sessions with refresh tokens
- `v_sessions` — all historical sessions
- `user_roles_permission_view` — flattened (user, role, permission) for fast permission checks

---

### Schema: `user_collection`

User collection management (cards a user owns).

**Typical Structure:**

| Table | Columns | Purpose |
|-------|---------|---------|
| `collections` | `collection_id` UUID PK, `user_id` UUID FK, `collection_name` TEXT, `description` TEXT, `is_active` BOOL | User collections (grouping) |
| `collection_items` | `item_id` UUID PK, `collection_id` UUID FK, `card_version_id` UUID FK, `finish_id` SMALLINT, `condition` VARCHAR, `purchase_price` NUMERIC, `currency_code` VARCHAR(3), `purchase_date` DATE, `language_id` SMALLINT | Individual cards in collections |

---

### Schema: `app_integration`

Third-party API credentials and OAuth tokens (eBay, Shopify, Scryfall).

**Typical Structure:**

| Table | Purpose |
|-------|---------|
| `oauth_credentials` | Store refresh tokens and scopes for external APIs |
| `api_key_store` | API keys for data providers |
| `webhook_subscriptions` | Track registered webhooks (e.g., for inventory sync) |

---

### Schema: `ops`

Operational metadata (pipeline runs, ingestion status, error tracking).

**File:** [`09_ops_schema.sql`](../../../src/automana/database/SQL/schemas/09_ops_schema.sql)

| Table | Purpose |
|-------|---------|
| `ingestion_runs` | Track Scryfall/MTGJson/MTGStock ETL pipeline executions |
| `ingestion_steps` | Per-step status (download, parse, load) with error details |
| `sanity_checks` | Health metrics (duplicate card count, referential integrity issues) |

---

## Entity-Relationship Diagram

High-level schema relationships (simplified):

```
user_management.users
    ├─ user_roles → roles → role_permissions → permissions
    ├─ sessions → refresh_tokens
    ├─ session_audit_logs (log table)
    └─ user_audit_logs (log table)

card_catalog.unique_cards_ref
    ├─ card_version (1:M)
    │   ├─ sets (via set_id)
    │   ├─ rarities_ref (via rarity_id)
    │   ├─ artists_ref (via illustration_artist)
    │   └─ pricing.mtg_card_products (1:1)
    │       └─ pricing.source_product (1:M)
    │           └─ pricing.price_observation (1:M) [Tier 1 — TimescaleDB]
    │
    ├─ card_types (M:M via unique_card_id)
    ├─ card_keyword (M:M via unique_card_id)
    └─ color_produced (M:M via unique_card_id)

pricing.print_price_daily [Tier 2 — TimescaleDB]
    └─ print_price_weekly [Tier 3 — TimescaleDB]

pricing.print_price_latest [Current snapshot]

user_collection.collections
    └─ collection_items (M:M to card_version via card_version_id)

app_integration.oauth_credentials
    └─ per-user API credentials
```

---

## Database Roles & Access Control

AutoMana uses PostgreSQL **role-based access control (RBAC)** with strict separation between DDL (schema changes) and DML (data operations).

**Principle:** Only the object owner can DROP or ALTER a table — so keeping DDL and DML in separate roles makes destructive operations impossible by design.

**Reference:** [`docs/DATABASE_ROLES.md`](../DATABASE_ROLES.md) · [`infra/db/init/02-app-roles.sql.tpl`](../../../infra/db/init/02-app-roles.sql.tpl)

### Role Hierarchy

```
db_owner (NOLOGIN)
    ├─ automana_admin (LOGIN) — member of db_owner + app_admin
    │   └─ Runs migrations (DDL)

app_admin (NOLOGIN)
    ├─ app_rw (NOLOGIN)
    │   ├─ app_backend (LOGIN) — FastAPI server
    │   └─ app_celery (LOGIN) — Celery workers
    ├─ app_ro (NOLOGIN)
    │   └─ app_readonly (LOGIN)
    └─ agent_reader (NOLOGIN) [restricted in prod]
        └─ app_agent (LOGIN)
```

### Actual RBAC SQL

**Create group roles (NOLOGIN):**

```sql
CREATE ROLE db_owner NOLOGIN;
CREATE ROLE app_admin NOLOGIN;
CREATE ROLE app_rw NOLOGIN;
CREATE ROLE app_ro NOLOGIN;
CREATE ROLE agent_reader NOLOGIN;
```

**Create login users with passwords:**

```sql
CREATE USER automana_admin PASSWORD 'secure_password';
CREATE USER app_backend PASSWORD 'secure_password';
CREATE USER app_celery PASSWORD 'secure_password';
CREATE USER app_readonly PASSWORD 'secure_password';
CREATE USER app_agent PASSWORD 'secure_password';
```

**Wire up role membership:**

```sql
-- automana_admin: migration runner (db_owner + app_admin)
GRANT db_owner TO automana_admin;
GRANT app_admin TO automana_admin;

-- app_admin: inherits read/write (but not ownership)
GRANT app_rw TO app_admin;
GRANT app_ro TO app_admin;

-- Application users
GRANT app_rw TO app_backend, app_celery;
GRANT app_ro TO app_readonly;
GRANT agent_reader TO app_agent;
```

**Grant schema and table privileges:**

```sql
-- Per-schema: grant USAGE to all roles
GRANT USAGE ON SCHEMA card_catalog TO app_admin, app_rw, app_ro, agent_reader;
GRANT CREATE ON SCHEMA card_catalog TO db_owner;

-- app_admin: full DML (SELECT, INSERT, UPDATE, DELETE, TRUNCATE)
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA card_catalog TO app_admin;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA card_catalog TO app_admin;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_admin;

-- app_rw: standard read/write (no TRUNCATE)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA card_catalog TO app_rw;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA card_catalog TO app_rw;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_rw;

-- app_ro / agent_reader: read-only
GRANT SELECT ON ALL TABLES IN SCHEMA card_catalog TO app_ro, agent_reader;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_ro, agent_reader;

-- Future objects created by db_owner automatically inherit grants
ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA card_catalog
  GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO app_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA card_catalog
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE db_owner IN SCHEMA card_catalog
  GRANT SELECT ON TABLES TO app_ro, agent_reader;
```

### Privilege Summary

| Role | SELECT | INSERT | UPDATE | DELETE | CREATE | DROP | ALTER |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `db_owner` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `app_admin` | ✓ | ✓ | ✓ | ✓ | — | — | — |
| `app_rw` | ✓ | ✓ | ✓ | ✓ | — | — | — |
| `app_ro` | ✓ | — | — | — | — | — | — |
| `agent_reader` | ✓ | — | — | — | — | — | — |

---

## Indexing Strategy

### Index Design Principles

1. **Exact Match First**: Indexes on columns used in equality predicates (WHERE col = value).
2. **Range Queries**: Include ordering columns for range scans and LIMIT queries.
3. **Join Columns**: Index foreign keys to speed up JOINs.
4. **Covering Indexes**: When economical, include non-key columns to enable index-only scans.
5. **Avoid Over-Indexing**: Every index slows writes and increases storage. Only index columns that appear in WHERE/JOIN/ORDER BY clauses.

### Core Indexes

#### Card Catalog

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `PK` | `unique_cards_ref` | `unique_card_id` | Identity |
| `UNIQUE` | `unique_cards_ref` | `card_name` | Uniqueness enforcement |
| `idx_card_version_set_collector` | `card_version` | `(set_id, collector_number)` | Set + collector lookups (Scryfall ingestion) |
| `idx_card_version_scryfall_id` | `card_version` | `(external_id_type, external_id)` | Fast Scryfall ID lookups |
| `idx_card_version_unique_id` | `card_version` | `unique_card_id` | Reverse join to unique_cards_ref |
| `idx_artists_name` | `artists_ref` | `artist_name` | Artist search |
| `idx_keywords` | `keywords_ref` | `keyword_name` | Keyword lookup |

#### Pricing (TimescaleDB)

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `idx_price_date` | `price_observation` | `(source_product_id, ts_date DESC)` | Recent prices for a product |
| `idx_ppd_card_source_date` | `print_price_daily` | `(card_version_id, source_id, price_date DESC)` | Card price history |
| `idx_ppd_date_dims` | `print_price_daily` | `(price_date, finish_id, condition_id, language_id)` | Bulk queries by date and dimensions |
| `idx_ppw_card_source_week` | `print_price_weekly` | `(card_version_id, source_id, price_week DESC)` | Weekly trends |
| `idx_ppw_week_dims` | `print_price_weekly` | `(price_week, finish_id, condition_id, language_id)` | Bulk queries by week and dimensions |
| `idx_ppl_card_source` | `print_price_latest` | `(card_version_id, source_id)` | Current price fast path |

**TimescaleDB Automatic Indexes:**
- Hypertables automatically create indexes on the time column (`ts_date`, `price_date`, `price_week`) for chunk pruning.

#### User Management

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `PK` | `users` | `unique_id` | Identity |
| `UNIQUE` | `users` | `username` | Login |
| `UNIQUE` | `users` | `email` | Email lookups |
| `idx_sessions_user` | `sessions` | `user_id` | Sessions for a user |
| `idx_sessions_expires` | `sessions` | `expires_at` | Cleanup of expired sessions |

### Index Maintenance

**Bloat Monitoring:**
```sql
SELECT schemaname, tablename, indexname, 
       ROUND(100.0 * (OTTA - OVP) / OTTA, 2) AS waste_ratio
FROM pgstattuple_approx(...)
WHERE waste_ratio > 10;  -- flag if > 10% waste
```

**Reindex Schedule:**
- **Automated:** PostgreSQL 9.6+ handles index cleanup automatically. Manual reindex rarely needed.
- **Manual trigger:** If a table has sustained high delete/update rate, consider `REINDEX CONCURRENTLY` on that table's largest indexes.

---

## Constraints & Triggers

### NOT NULL Constraints

Applied to all mandatory business fields:
- `card_version.unique_card_id`, `set_id`, `rarity_id`
- `pricing.price_observation.ts_date`, `source_product_id`
- `user_management.users.username`, `email`, `unique_id`

### UNIQUE Constraints

| Table | Columns | Purpose |
|-------|---------|---------|
| `unique_cards_ref` | `card_name` | Card identity |
| `card_version` | `(set_id, collector_number)` | Print identity |
| `users` | `username`, `email` | Login uniqueness |
| `sessions` | `device_id` | Device binding |
| `rarities_ref` | `rarity_name` | Dimension uniqueness |
| `colors_ref` | `color_name` | |
| `artists_ref` | `artist_name` | |

### FOREIGN KEY Constraints

**All FKs use CASCADE on delete** (except where noted):
- `card_version.unique_card_id` → `unique_cards_ref(unique_card_id)` [CASCADE]
- `card_version.set_id` → `sets(set_id)` [CASCADE]
- `pricing.source_product.product_id` → `product_ref(product_id)` [CASCADE]
- `sessions.user_id` → `users(unique_id)` [CASCADE]

**Why CASCADE?** Deleting a card should cascade to all its versions and prices. Deleting a user should cascade to sessions and tokens. Explicit cascades prevent orphaned rows.

### CHECK Constraints

| Table | Constraint | Purpose |
|-------|-----------|---------|
| `price_observation` | `list_low_cents IS NULL OR list_low_cents >= 0` | Prices non-negative |
| `price_observation` | `sold_avg_cents IS NULL OR sold_avg_cents >= 0` | |
| `print_price_daily` | `list_low_cents >= 0` | |
| `card_types` | `type_category IN ('type', 'subtype', 'supertype')` | Valid enum values |

### Triggers

**`trigger_log_user_status_change`** (on `user_management.users`)
- Fires on `UPDATE OF disabled`
- Logs to `user_audit_logs` when user is disabled/enabled
- Reads `app.current_user_id` and `app.source_ip` from session GUCs

**`trigger_log_user_role_insert` / `trigger_log_user_role_delete`** (on `user_management.user_roles`)
- Fires on INSERT and DELETE
- Logs role assignments and removals to `user_role_audit_logs`

**GUC Setup (from application layer):**
```sql
SET LOCAL app.current_user_id = '...'::uuid;
SET LOCAL app.source_ip = '...';
-- Now trigger logic can access these via current_setting()
UPDATE user_management.users SET disabled = true WHERE unique_id = ...;
```

---

## TimescaleDB Hypertables

### Why TimescaleDB?

1. **Automatic Partitioning**: Data partitioned by time range (7-day chunks) without manual maintenance.
2. **Compression**: Older data automatically compressed to ~1/10th original size.
3. **Parallel Queries**: Distributed scans across chunks for faster range queries.
4. **Retention Policies**: Automatic deletion of data older than retention window.

### Hypertables in AutoMana

#### `pricing.price_observation` (Tier 1)

```sql
SELECT create_hypertable(
    'pricing.price_observation',
    by_range('ts_date'),
    if_not_exists => TRUE
);

SELECT set_chunk_time_interval('pricing.price_observation', INTERVAL '7 days');

ALTER TABLE pricing.price_observation
  SET (timescaledb.compress,
       timescaledb.compress_segmentby = 'source_product_id, price_type_id, finish_id',
       timescaledb.compress_orderby = 'ts_date DESC');

SELECT add_compression_policy(
    'pricing.price_observation',
    INTERVAL '180 days'
);
```

**Impact:** 500M raw rows compressed to ~50M over time. Typical query latency: <100ms for full year of data.

#### `pricing.print_price_daily` (Tier 2)

```sql
SELECT create_hypertable(
    'pricing.print_price_daily',
    by_range('price_date', INTERVAL '7 days'),
    if_not_exists => TRUE
);

ALTER TABLE pricing.print_price_daily
    SET (timescaledb.compress,
         timescaledb.compress_segmentby = 'card_version_id, source_id, finish_id',
         timescaledb.compress_orderby = 'price_date DESC');

SELECT add_compression_policy(
    'pricing.print_price_daily',
    INTERVAL '30 days',
    if_not_exists => TRUE
);
```

#### `pricing.print_price_weekly` (Tier 3)

```sql
SELECT create_hypertable(
    'pricing.print_price_weekly',
    by_range('price_week', INTERVAL '28 days'),
    if_not_exists => TRUE
);

SELECT add_compression_policy(
    'pricing.print_price_weekly',
    INTERVAL '7 days',
    if_not_exists => TRUE
);
```

### Chunk Visibility

```sql
-- View all chunks
SELECT chunk_name, range_start, range_end, table_bytes
FROM timescaledb_information.chunks
WHERE hypertable_name = 'price_observation';

-- View compression status
SELECT chunk_name, is_compressed, before_compression_total_bytes
FROM timescaledb_information.chunks
WHERE hypertable_name = 'price_observation'
  AND before_compression_total_bytes IS NOT NULL;
```

---

## Backup & Recovery

### Backup Strategy

**Full Database Backup (pg_dump):**
```bash
pg_dump -Fc -v automana > automana_$(date +%Y%m%d_%H%M%S).dump
```

**Advantages:**
- Works with TimescaleDB (TimescaleDB is a PostgreSQL extension, so pg_dump handles hypertables)
- Restores to any PostgreSQL version with TimescaleDB installed
- Supports incremental restore (tables, schemas, etc.)

**Backup Frequency:**
- Daily incremental (with WAL archiving) for dev/staging
- Continuous WAL archiving for production
- Full backup weekly for archival

**Related:** [`docs/DEPLOYMENT.md`](../DEPLOYMENT.md) — backup container setup

### Recovery Procedures

**Full Database Restore:**
```bash
pg_restore -d automana automana_20250501_120000.dump
```

**Point-in-Time Recovery (PITR):**
1. Enable WAL archiving in `postgresql.conf`:
   ```
   wal_level = replica
   archive_mode = on
   archive_command = 'cp %p /backups/wal_archive/%f'
   ```
2. Restore from backup to a target time:
   ```bash
   pg_restore -d automana_restored automana_latest.dump
   ```
   Then replay WAL up to desired time using `pg_waldump`.

**Table-Level Recovery:**
```bash
pg_restore -t card_version -d automana automana.dump  -- restores single table
```

### Verification & Sanity Checks

**Post-restore validation:**
```sql
-- Check referential integrity
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'card_catalog'
ORDER BY constraint_name;

-- Verify hypertable structure
SELECT * FROM timescaledb_information.hypertables
WHERE hypertable_schema = 'pricing';

-- Sample row counts
SELECT schemaname, tablename, n_live_tup
FROM pg_stat_user_tables
WHERE schemaname IN ('card_catalog', 'pricing', 'user_management')
ORDER BY schemaname, tablename;
```

---

## See Also

- [`docs/MIGRATIONS.md`](MIGRATIONS.md) — Safe migration patterns and examples
- [`docs/REPOSITORY_PATTERN.md`](REPOSITORY_PATTERN.md) — How repositories interact with this schema
- [`docs/DATABASE_ROLES.md`](../DATABASE_ROLES.md) — Role-based access control
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — Layered architecture overview
