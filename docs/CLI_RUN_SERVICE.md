# Developer Tools — CLI and TUI

AutoMana ships two interactive developer tools for running and testing services without starting the full API server or a Celery worker. Both share the same bootstrap logic ([`src/automana/tools/tui/shared.py`](../src/automana/tools/tui/shared.py)) and exercise the exact same service layer code paths as production.

| Tool | Command | Best for |
|---|---|---|
| CLI | `automana-run` | Scripting, piping, CI, quick one-off calls |
| TUI | `automana-tui` | Interactive exploration, visual output, API testing |

---

## automana-run — Service Runner CLI

### Overview

`automana-run` is a command-line tool for calling any registered service directly, without starting the FastAPI server or a Celery worker. It boots the same database pool and `ServiceManager` used by the worker, executes the service, and prints the result as JSON to stdout.

It is the fastest way to:
- Test a service in isolation during development
- Inspect the output of a pipeline step
- Diagnose a failing service with live data
- Explore which services are available
- Chain multiple pipeline steps together manually

**Source:** [`src/automana/tools/run_service.py`](../src/automana/tools/run_service.py)

---

### Setup

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

### Prerequisites

The tool needs a live PostgreSQL instance. Start just the database container — the full
stack is not required:

```bash
docker compose -f deploy/docker-compose.dev.yml up -d postgres
```

The `.env.dev` config already points to `localhost:5433`, which is the host-mapped port
for the dev Postgres container.

---

### Usage

```
automana-run [SERVICE_PATH] [--key value ...] [--db-user USER] [--db-password PASSWORD] [--raw] [--list-users]
```

| Argument | Description |
|---|---|
| `SERVICE_PATH` | Dot-separated service key (e.g. `staging.scryfall.get_bulk_data_uri`). Omit to list all services. |
| `--key value` | Any number of keyword arguments passed to the service. Values are auto-cast (see below). |
| `--db-user USER` | Connect as this database user instead of the default (`app_backend`). See `--list-users`. |
| `--db-password PASSWORD` | Password for `--db-user`. If omitted the matching secret file is resolved automatically. |
| `--list-users` | Print all available database users with their roles and exit. No DB connection required. |
| `--raw` | Print `repr(result)` instead of JSON (useful when the result is not serialisable). |

---

### Examples

#### List available DB users

```bash
automana-run --list-users
```

Output:
```
Available DB users:

  app_backend          app_rw                    FastAPI application — SELECT / INSERT / UPDATE / DELETE
  app_celery           app_rw                    Celery workers     — SELECT / INSERT / UPDATE / DELETE
  automana_admin       db_owner + app_admin      Migration runner   — full DDL + DML
  app_readonly         app_ro                    Read-only queries  — SELECT only
  app_agent            agent_reader              AI agent           — SELECT, restricted schemas in prod
```

This flag does not open a database connection — it exits immediately.

---

#### List all registered services

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

#### Call a service

```bash
automana-run staging.scryfall.get_bulk_data_uri --ingestion_run_id 42
```

Stderr (progress):
```
[automana-run] step 1/1: staging.scryfall.get_bulk_data_uri
[automana-run] kwargs   : {'ingestion_run_id': 42}
[automana-run] elapsed  : 14.3 ms
```

Stdout (result):
```json
{
  "bulk_uri": "https://api.scryfall.com/bulk-data"
}
```

#### Search cards

```bash
automana-run card_catalog.card.search \
  --name "Black Lotus" \
  --limit 5 \
  --digital false
```

#### Start a pipeline run

```bash
automana-run staging.scryfall.start_pipeline \
  --pipeline_name scryfall_daily \
  --source_name scryfall \
  --run_key scryfall_daily:2026-03-29
```

#### Chain multiple steps

Multiple service keys can be passed on one command line. Each bare (non-flag) token after the first is treated as the start of a new step. The result dict of each step is merged into the accumulated context and passed to the next step; explicit per-step flags take precedence.

```bash
automana-run staging.scryfall.download_bulk_manifests \
             --ingestion_run_id 1 --bulk_uri https://api.scryfall.com/bulk-data \
             staging.scryfall.update_data_uri_in_ops_repository \
             --ingestion_run_id 1
```

Output shows each step's progress on stderr and the final step's result on stdout.

#### Pipe result into jq

The JSON result goes to **stdout** and progress messages go to **stderr**, so piping works cleanly:

```bash
automana-run staging.scryfall.get_bulk_data_uri --ingestion_run_id 42 | jq .bulk_uri
```

---

### Value Auto-Casting

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

### How It Works

1. **Bootstrap** — Creates an asyncpg connection pool and initialises `ServiceManager` (identical to the Celery worker bootstrap in `worker/ressources.py`).
2. **Service resolution** — `ServiceManager` looks up the service key in `ServiceRegistry`, imports the module, and injects the required DB and API repositories.
3. **Execution** — Calls the service function inside a database transaction, exactly as it would be called from an API router or a Celery task.
4. **Teardown** — Closes the connection pool cleanly after the call.

Because the full service stack is initialised, the tool exercises exactly the same code path as production — there is no mocking or test-mode behaviour.

---

### Caveats

- **Side effects are real.** Calling a write service (e.g. `staging.scryfall.start_pipeline`) inserts rows into the live database. Use the dev database only.
- **No chain context.** The Celery `run_service` task merges the result of each step into a shared `context` dict that flows through the chain. When calling a single service with the CLI, only the kwargs you provide are passed — it does not simulate the chain automatically. Supply any required upstream keys manually as flags, or use the multi-step chaining syntax described above.
- **API services hit the real network.** Steps that call the Scryfall API (e.g. `staging.scryfall.download_bulk_manifests`) make live HTTP requests.

---

## automana-tui — Terminal User Interface

### Overview

`automana-tui` is an interactive, full-screen terminal application built with [Textual](https://textual.textualize.io/). It provides a visual alternative to `automana-run` and adds a live Celery launcher and an API endpoint tester — all in a single keyboard-driven UI.

**Source:** [`src/automana/tools/tui/app.py`](../src/automana/tools/tui/app.py)

**Entry point (registered in `pyproject.toml`):**

```toml
automana-tui = "automana.tools.tui.app:main"
```

**Dependency:** `textual>=0.80.0` (listed in `pyproject.toml`).

---

### Launch

```bash
# From the project root, with the venv activated
automana-tui
```

The same prerequisites apply as for `automana-run`: PostgreSQL must be reachable. Start the database container first if it is not already running:

```bash
docker compose -f deploy/docker-compose.dev.yml up -d postgres
```

The TUI calls the same `bootstrap()` helper as the CLI (`src/automana/tools/tui/shared.py`), so it initialises an asyncpg pool and the `ServiceManager` on startup.

---

### Layout

The application opens to a three-tab interface. Navigate between tabs with the keyboard shortcuts shown in the footer.

| Key | Tab |
|---|---|
| `1` | Services |
| `2` | Celery |
| `3` | API |
| `Ctrl+C` | Quit |

---

### Tab 1 — Services

**Source:** [`src/automana/tools/tui/panels/services.py`](../src/automana/tools/tui/panels/services.py)

Mirrors the functionality of `automana-run` in a visual form.

```
┌─ ServiceTree ──┬─ Detail ──────────────────────────────┐
│  ▶ analytics   │  service: staging.scryfall.start...   │
│  ▼ staging     │                                       │
│    ▶ scryfall  │  [KwargForm inputs]                   │
│  ▶ ops         │                                       │
│                │  DB user: [Select ▼]  [ Run ↵ ]      │
├────────────────┴───────────────────────────────────────┤
│  JsonViewer (output + call history)                    │
└────────────────────────────────────────────────────────┘
```

**Left column — ServiceTree**

A collapsible tree widget ([`src/automana/tools/tui/widgets/service_tree.py`](../src/automana/tools/tui/widgets/service_tree.py)) that groups all services registered in `ServiceRegistry` by their top-level domain prefix (e.g. `analytics`, `staging`, `card_catalog`). Leaf nodes show the tail of the key; selecting a leaf loads that service into the form.

**Right column — KwargForm**

A dynamic form ([`src/automana/tools/tui/widgets/kwarg_form.py`](../src/automana/tools/tui/widgets/kwarg_form.py)) built by inspecting the selected service function's signature via `inspect.signature`. One labelled `Input` field is rendered per parameter (excluding `self` and `context`). If the service takes no parameters, a `(no parameters)` notice is shown.

**DB user selector**

A drop-down ([`src/automana/tools/tui/widgets/db_user_select.py`](../src/automana/tools/tui/widgets/db_user_select.py)) listing every DB user defined in `shared.DB_USERS`. The selected user is passed to `ServiceManager.execute_service`. Default: `app_backend`.

**Run button / keyboard shortcut**

Press the `Run ↵` button or `Ctrl+R` to execute the selected service with the current form values. Values are auto-cast using the same `coerce()` helper as the CLI.

**Bottom panel — JsonViewer**

A syntax-highlighted scrollable log ([`src/automana/tools/tui/widgets/json_viewer.py`](../src/automana/tools/tui/widgets/json_viewer.py)) that displays the service result as pretty-printed JSON (Monokai theme), elapsed time, and error tracebacks.

---

### Tab 2 — Celery

**Source:** [`src/automana/tools/tui/panels/celery.py`](../src/automana/tools/tui/panels/celery.py)

Provides a visual launcher for the Celery pipeline tasks defined in `worker/tasks/pipelines.py`.

```
┌─ Task list ─────────────┬─ Pipeline steps ──────────────┐
│  Scryfall daily pipeline│  Step 1: start_pipeline       │
│  MTGJson daily pipeline │  Step 2: get_bulk_data_uri    │
│  MTGStock download ..   │  ...                          │
│                         │  [ Launch ]                   │
├─────────────────────────┴───────────────────────────────┤
│  Live status / output (JsonViewer)                      │
└─────────────────────────────────────────────────────────┘
```

**Known pipeline tasks displayed:**

| Label | Celery task name | Steps |
|---|---|---|
| Scryfall daily pipeline | `daily_scryfall_data_pipeline` | 10 steps |
| MTGJson daily pipeline | `daily_mtgjson_data_pipeline` | 3 steps |
| MTGStock download pipeline | `mtgStock_download_pipeline` | 6 steps |

Select a task from the list to see its ordered steps in the right column, then press **Launch** to dispatch it.

**Dispatch mechanism:** `celery call <task_name>` is invoked as a subprocess (`celery -A automana.worker.main:app call <task_name>`). This requires the `celery` command to be on the PATH (i.e. the venv must be activated) and the worker to be running.

**Status polling:** After launch, the panel polls `celery inspect active --json` every 3 seconds (up to ~2 minutes) and updates the JsonViewer with the live task state until the task ID disappears from the active list.

> The Celery worker must be running separately for launched tasks to execute. Start it with `celery -A automana.worker.main:app worker ...` or via `docker compose`.

---

### Tab 3 — API

**Source:** [`src/automana/tools/tui/panels/api.py`](../src/automana/tools/tui/panels/api.py)

An interactive HTTP client that introspects the running FastAPI server's `GET /openapi.json` and lets you call any endpoint directly.

```
┌─ Route tree ────────────┬─ Request form ────────────────┐
│  ▶ mtg                  │  GET /mtg/cards               │
│  ▶ users                │                               │
│  ▶ integrations         │  Base URL: [http://localhost..]│
│                         │  Bearer:   [___________]      │
│                         │  [params / body inputs]       │
│                         │  [ Send ]                     │
├─────────────────────────┴───────────────────────────────┤
│  Response (JsonViewer)                                  │
└─────────────────────────────────────────────────────────┘
```

**Route tree:** On mount, the panel fetches `<base_url>/openapi.json` and builds a collapsible tree of routes grouped by the first path segment. Each leaf shows the HTTP method (colour-coded) and path.

**Request form:** Selecting a route renders `Input` fields for each OpenAPI `parameters` entry. For `POST`/`PUT`/`PATCH` routes, a raw JSON body input is also shown. A Bearer token field is available for authenticated endpoints (value is masked).

**Default base URL:** `http://localhost:8000`. Change it in the `Base URL` input — the panel re-fetches the spec automatically on the next interaction.

**Sending a request:** `httpx` is used as the async HTTP client. The response status code (colour-coded green/red) and elapsed time are displayed, followed by the pretty-printed response body in the JsonViewer.

> The FastAPI server must be running separately. Start it with `uvicorn automana.api.main:app` or via `docker compose`.

---

### Shared Bootstrap

Both `automana-run` and `automana-tui` use the helpers in [`src/automana/tools/tui/shared.py`](../src/automana/tools/tui/shared.py):

- `bootstrap(db_user, db_password)` — initialises the asyncpg pool and `ServiceManager`; resolves the DB password from the matching secret file in `config/secrets/` if not supplied explicitly.
- `teardown(pool)` — closes the pool cleanly on exit.
- `coerce(value)` — casts a string to `bool`, `None`, `int`, `float`, or `str` in that order of preference.
- `DB_USERS` — the canonical dict of all supported database users, their roles, descriptions, and secret file names.
