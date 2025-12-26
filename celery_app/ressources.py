from contextlib import contextmanager
from backend.core.settings import get_settings, Settings
from backend.core.database import init_sync_pool, close_sync_pool
import os

_sync_pool = None
_settings: Settings | None = None

def init_db_pool() -> None:
    global _sync_pool, _settings
    if _settings is None:
        _settings = get_settings()
    if _sync_pool is None:
        _sync_pool = init_sync_pool(_settings)
    
def shutdown_db_pool() -> None:
    global _sync_pool
    if _sync_pool is not None:
        close_sync_pool(_sync_pool)
        _sync_pool = None

@contextmanager
def get_connection():
    global _sync_pool
    if _sync_pool is None:
        init_db_pool()

    # psycopg2-style pool:
    conn = _sync_pool.getconn()
    try:
        yield conn
        # optional: conn.commit() here if you want auto-commit behavior
    except Exception:
        # optional: conn.rollback() to be safe
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        _sync_pool.putconn(conn)