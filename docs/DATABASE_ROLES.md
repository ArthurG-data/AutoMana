# Database Roles & Access Control

## Overview

AutoMana uses PostgreSQL role-based access control (RBAC) with a strict separation between DDL (schema changes) and DML (data operations). The key principle is: **only the object owner can DROP or ALTER a table** — so keeping DDL and DML in separate roles makes destructive operations impossible for application users by design, not by policy.

**Source:** [`infra/db/init/02-app-roles.sql.tpl`](../infra/db/init/02-app-roles.sql.tpl)
**Migration (existing DBs):** [`database/SQL/migrations/10_rbac_db_owner.sql`](../src/automana/database/SQL/migrations/10_rbac_db_owner.sql)

---

## Role Hierarchy

```
db_owner  (NOLOGIN)          — owns all objects; DDL only
│
└── automana_admin  (LOGIN)  — migration runner; member of db_owner + app_admin

app_admin  (NOLOGIN)         — full DML; cannot DROP (not an owner)
├── app_rw  (NOLOGIN)        — SELECT / INSERT / UPDATE / DELETE
│   ├── app_backend  (LOGIN)
│   └── app_celery   (LOGIN)
├── app_ro  (NOLOGIN)        — SELECT only
│   └── app_readonly  (LOGIN)
└── agent_reader  (NOLOGIN)  — SELECT only (restricted schemas in prod)
    └── app_agent  (LOGIN)
```

---

## Group Roles

### `db_owner`
- **Type:** NOLOGIN (no direct login)
- **Owns:** all tables, sequences, functions, schemas
- **Can:** `CREATE`, `DROP`, `ALTER` any object it owns
- **Cannot:** log in directly
- **Used by:** `automana_admin` (via membership) when running migrations

This is the only role in the system that can destroy or restructure schema objects. Keeping it NOLOGIN means no application connection can accidentally (or maliciously) drop a table.

### `app_admin`
- **Type:** NOLOGIN
- **Owns:** nothing
- **Can:** `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE` on all tables in all schemas; `EXECUTE` on all functions; `USAGE` + `UPDATE` on all sequences
- **Cannot:** `CREATE`, `DROP`, or `ALTER` any table, schema, or function — because it does not own them
- **Used by:** `automana_admin` for day-to-day data operations

The inability to DROP is structural: PostgreSQL only allows the owner to drop an object. Since `app_admin` is never granted ownership, no code running as `app_admin` can destroy data structures.

### `app_rw`
- **Type:** NOLOGIN
- **Can:** `SELECT`, `INSERT`, `UPDATE`, `DELETE` on all tables; `USAGE` + `UPDATE` on sequences; `EXECUTE` on functions
- **Cannot:** `TRUNCATE`, `DROP`, `ALTER`, or `CREATE`
- **Used by:** `app_backend` (FastAPI), `app_celery` (Celery workers)

### `app_ro`
- **Type:** NOLOGIN
- **Can:** `SELECT` on all tables; `EXECUTE` on functions
- **Cannot:** write anything
- **Used by:** `app_readonly`

### `agent_reader`
- **Type:** NOLOGIN
- **Can:** `SELECT` on tables; `EXECUTE` on functions
- **Cannot:** write anything
- **Prod restriction:** `USAGE` is revoked on `user_management`, `user_collection`, `app_integration`, `pricing` — agent cannot see those schemas at all in production
- **Used by:** `app_agent`

---

## Login Users

| User | Role memberships | Purpose |
|---|---|---|
| `automana_admin` | `db_owner`, `app_admin` | Run migrations (DDL) and inspect/repair data (DML) |
| `app_backend` | `app_rw` | FastAPI application server |
| `app_celery` | `app_rw` | Celery workers (ETL pipelines, background jobs) |
| `app_readonly` | `app_ro` | Read-only queries, reporting tools |
| `app_agent` | `agent_reader` | AI agent queries (limited schema access in prod) |

Passwords are never stored in source code. They are injected at container startup from Docker secrets mounted at `/run/secrets/`.

---

## Privilege Matrix

### Tables

| Role | SELECT | INSERT | UPDATE | DELETE | TRUNCATE | CREATE | DROP | ALTER |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `db_owner` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `app_admin` | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — |
| `app_rw` | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| `app_ro` | ✓ | — | — | — | — | — | — | — |
| `agent_reader` | ✓ | — | — | — | — | — | — | — |

### Sequences

| Role | USAGE | SELECT (currval) | UPDATE (nextval) |
|---|:---:|:---:|:---:|
| `db_owner` | ✓ | ✓ | ✓ |
| `app_admin` | ✓ | ✓ | ✓ |
| `app_rw` | ✓ | ✓ | ✓ |
| `app_ro` | — | — | — |
| `agent_reader` | — | — | — |

### Functions

| Role | EXECUTE |
|---|:---:|
| `db_owner` | ✓ |
| `app_admin` | ✓ |
| `app_rw` | ✓ |
| `app_ro` | ✓ |
| `agent_reader` | ✓ |

### Materialized Views

PostgreSQL has no `REFRESH` privilege. Refresh requires object ownership.

| Role | SELECT | REFRESH |
|---|:---:|:---:|
| `db_owner` | ✓ | ✓ (owner) |
| `app_admin` | ✓ | — |
| `app_rw` | ✓ | — |
| `app_ro` | ✓ | — |
| `agent_reader` | ✓ | — |

To refresh a materialized view from application code, the query must be executed as `automana_admin` (which has `db_owner` membership), not as `app_backend` or `app_celery`.

---

## Schemas

The following schemas exist. All are owned by `db_owner`.

| Schema | Purpose |
|---|---|
| `card_catalog` | MTG sets, cards, card versions |
| `user_management` | Users, authentication, sessions |
| `user_collection` | User card collections and inventory |
| `app_integration` | eBay, Shopify, Scryfall, MTGJson integration data |
| `pricing` | Pricing rules and strategies |
| `markets` | Market price data |
| `ops` | Pipeline runs, ingestion tracking, metrics |
| `public` | Extensions only (e.g. `uuid-ossp`, `pgvector`) |

In **production**, `agent_reader` has `USAGE` revoked on `user_management`, `user_collection`, `app_integration`, and `pricing` — the agent role can only see `card_catalog`, `markets`, and `ops`.

> **Maintenance scripts:** The three SQL sanity-check scripts in `src/automana/database/SQL/maintenance/` read across `card_catalog`, `ops`, and `pricing`. In production, `app_agent` (via `agent_reader`) lacks `USAGE` on `pricing` and cannot run `scryfall_integrity_checks.sql`. Use `app_readonly` (`app_ro`) or `automana_admin` to execute these scripts.

---

## Public Schema

The `public` schema is locked down:
- `CREATE` is revoked from all roles except `db_owner`
- `USAGE` is granted to `app_admin`, `app_rw`, `app_ro`, `agent_reader` (needed for extension functions like `uuid_generate_v4()`)
- No application role can add objects to `public`

---

## Adding a New Migration

All schema changes must run as `automana_admin` (which has `db_owner` membership). After creating new tables or sequences, grants to `app_admin` and `app_rw` are applied automatically via `ALTER DEFAULT PRIVILEGES` — no manual `GRANT` is needed for routine migrations.

If you create a new schema, add it to the `schemas` array in `02-app-roles.sql.tpl` and re-run the bootstrap, or add explicit grants in your migration file.

---

## Troubleshooting: `permission denied for table <name>`

**Symptom:** `app_celery` or `app_backend` gets error code `42501` (`permission denied for table <name>`) even though `app_rw` should have access to that schema.

**Root cause:** `ALTER DEFAULT PRIVILEGES` only covers tables created *after* the privilege statement was issued. If the grants migration (e.g. migration 13) was applied before a new table was added to the schema, that table is not retroactively covered.

**Fix:** Create a new numbered migration that re-applies grants to the affected schema:

```sql
-- Re-apply grants on card_catalog (idempotent — safe to run multiple times)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA card_catalog TO app_rw;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA card_catalog TO app_rw;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA card_catalog TO app_rw;

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA card_catalog TO app_admin;

GRANT SELECT ON ALL TABLES IN SCHEMA card_catalog TO app_ro, agent_reader;
```

`GRANT ... ON ALL TABLES IN SCHEMA` is idempotent — re-running it on a table that already has grants is a no-op.

See migrations `13_grant_card_catalog.sql` and `14_grant_card_catalog_sets.sql` for real examples of this pattern.