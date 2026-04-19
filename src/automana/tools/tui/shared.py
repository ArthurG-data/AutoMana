"""
Shared bootstrap/teardown helpers for the AutoMana TUI and CLI tools.

Both automana-run (CLI) and automana-tui (TUI) boot the same DB pool and
ServiceManager.  Centralising the logic here prevents drift between the two.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# user → (role, description, secret_file)
DB_USERS: dict[str, tuple[str, str, str]] = {
    "app_backend":    ("app_rw",               "FastAPI application — SELECT / INSERT / UPDATE / DELETE", "backend_db_password.txt"),
    "app_celery":     ("app_rw",               "Celery workers     — SELECT / INSERT / UPDATE / DELETE",  "celery_db_password.txt"),
    "automana_admin": ("db_owner + app_admin", "Migration runner   — full DDL + DML",                    "admin_db_password.txt"),
    "app_readonly":   ("app_ro",               "Read-only queries  — SELECT only",                        "readonly_db_password.txt"),
    "app_agent":      ("agent_reader",         "AI agent           — SELECT, restricted schemas in prod", "agent_db_password.txt"),
}


async def bootstrap(db_user: str | None = None, db_password: str | None = None) -> Any:
    """Initialise asyncpg pool and ServiceManager.  Returns the pool."""
    from automana.core.database import init_async_pool
    from automana.core.QueryExecutor import AsyncQueryExecutor
    from automana.core.service_manager import ServiceManager
    from automana.core.settings import get_settings

    if db_user:
        os.environ["APP_BACKEND_DB_USER"] = db_user
        if not db_password and db_user in DB_USERS:
            secret_file = DB_USERS[db_user][2]
            for candidate in [
                Path.cwd() / "config" / "secrets" / secret_file,
                Path(__file__).resolve().parents[4] / "config" / "secrets" / secret_file,
            ]:
                if candidate.exists():
                    os.environ["POSTGRES_PASSWORD_FILE"] = str(candidate)
                    break

    if db_password:
        os.environ["POSTGRES_PASSWORD"] = db_password

    get_settings.cache_clear()
    settings = get_settings()
    pool = await init_async_pool(settings)
    await ServiceManager.initialize(pool, query_executor=AsyncQueryExecutor())
    return pool


async def teardown(pool: Any) -> None:
    """Close the asyncpg connection pool cleanly."""
    from automana.core.database import close_async_pool
    await close_async_pool(pool)


def coerce(value: str) -> Any:
    """Cast a CLI/form string to the most specific Python type."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in ("null", "none"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
