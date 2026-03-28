# automana-run — Service Runner CLI

## Overview

`automana-run` is a command-line tool for calling any registered service directly, without starting the FastAPI server or a Celery worker. It boots the same database pool and `ServiceManager` used by the worker, executes the service, and prints the result as JSON to stdout.

It is the fastest way to:
- Test a service in isolation during development
- Inspect the output of a pipeline step
- Diagnose a failing service with live data
- Explore which services are available

**Source:** [`src/automana/tools/run_service.py`](../src/automana/tools/run_service.py)

---

## Setup

The tool is installed as a console script entry point. It must be installed inside the project's virtual environment.

```bash
cd /path/to/AutoMana

# install (or reinstall after changes to pyproject.toml)
.venv/bin/pip install -e .

# activate the venv so the command is on your PATH
source .venv/bin/activate
```

> Always run from the **project root**. Settings resolution uses `Path.cwd()` to locate
> `config/env/.env.dev` and `config/secrets/backend_db_password.txt`.

---

## Prerequisites

The tool needs a live PostgreSQL instance. Start just the database container — the full
stack is not required:

```bash
docker compose -f deploy/docker-compose.dev.yml up -d postgres
```

The `.env.dev` config already points to `localhost:5433`, which is the host-mapped port
for the dev Postgres container.

---

## Usage

```
automana-run [SERVICE_PATH] [--key value ...]
```

| Argument | Description |
|---|---|
| `SERVICE_PATH` | Dot-separated service key (e.g. `staging.scryfall.get_bulk_data_uri`). Omit to list all services. |
| `--key value` | Any number of keyword arguments passed to the service. Values are auto-cast (see below). |
| `--raw` | Print `repr(result)` instead of JSON (useful when the result is not serialisable). |

---

## Examples

### List all registered services

```bash
automana-run
```

Output:
```
47 registered services:

  analytics.daily_summary.generate_report
  card_catalog.card.create
  card_catalog.card.create_many
  card_catalog.card.delete
  card_catalog.card.get
  card_catalog.card.process_large_json
  card_catalog.card.search
  card_catalog.set.add
  ...
```

### Call a service

```bash
automana-run staging.scryfall.get_bulk_data_uri --ingestion_run_id 42
```

Stderr (progress):
```
[automana-run] service  : staging.scryfall.get_bulk_data_uri
[automana-run] kwargs   : {'ingestion_run_id': 42}
[automana-run] elapsed  : 14.3 ms
[automana-run] result type: dict
```

Stdout (result):
```json
{
  "bulk_uri": "https://api.scryfall.com/bulk-data"
}
```

### Search cards

```bash
automana-run card_catalog.card.search \
  --name "Black Lotus" \
  --limit 5 \
  --digital false
```

### Start a pipeline run

```bash
automana-run staging.scryfall.start_pipeline \
  --pipeline_name scryfall_daily \
  --source_name scryfall \
  --run_key scryfall_daily:2026-03-29
```

### Pipe result into jq

The JSON result goes to **stdout** and progress messages go to **stderr**, so piping works cleanly:

```bash
automana-run staging.scryfall.get_bulk_data_uri --ingestion_run_id 42 | jq .bulk_uri
```

---

## Value Auto-Casting

CLI arguments are always received as strings. The tool automatically casts them to the most specific Python type before passing to the service:

| Input string | Python type | Python value |
|---|---|---|
| `42` | `int` | `42` |
| `3.14` | `float` | `3.14` |
| `true` / `True` | `bool` | `True` |
| `false` / `False` | `bool` | `False` |
| `null` / `none` | `NoneType` | `None` |
| `"Black Lotus"` | `str` | `"Black Lotus"` |

Both `--key value` and `--key=value` forms are accepted.

---

## How It Works

1. **Bootstrap** — Creates an asyncpg connection pool and initialises `ServiceManager` (identical to the Celery worker bootstrap in `worker/ressources.py`).
2. **Service resolution** — `ServiceManager` looks up the service key in `ServiceRegistry`, imports the module, and injects the required DB and API repositories.
3. **Execution** — Calls the service function inside a database transaction, exactly as it would be called from an API router or a Celery task.
4. **Teardown** — Closes the connection pool cleanly after the call.

Because the full service stack is initialised, the tool exercises exactly the same code path as production — there is no mocking or test-mode behaviour.

---

## Caveats

- **Side effects are real.** Calling a write service (e.g. `staging.scryfall.start_pipeline`) inserts rows into the live database. Use the dev database only.
- **No chain context.** The Celery `run_service` task merges the result of each step into a shared `context` dict that flows through the chain. The CLI passes only the kwargs you provide — it does not simulate the chain. If a service expects keys produced by a previous step, supply them manually as flags.
- **API services hit the real network.** Steps that call the Scryfall API (e.g. `staging.scryfall.download_bulk_manifests`) make live HTTP requests.