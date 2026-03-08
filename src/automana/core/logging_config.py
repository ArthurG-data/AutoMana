from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from automana.core.logging_context import get_request_id, get_task_id

_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "message", "asctime"
}

class ContextFilter(logging.Filter):
    """Logging filter to inject request_id and task_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.task_id = get_task_id()
        record.service = os.getenv("SERVICE_NAME", "unknown")
        record.env = os.getenv("APP_ENV", "dev")
        return True
    
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "service": getattr(record, "service", None),
            "env": getattr(record, "env", None),
            "request_id": getattr(record, "request_id", None),
            "task_id": getattr(record, "task_id", None),
            "service_path": getattr(record, "service_path", None),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k in _RESERVED or k.startswith("_"):
                continue
            if k not in payload:
                payload[k] = v

        return json.dumps(payload, default=str)
    
def configure_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_automana_configured", False):
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    as_json = os.getenv("LOG_JSON", "1").lower() in {"1", "true", "yes"}

    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter() if as_json else logging.Formatter(
        "%(asctime)s %(levelname)s %(service)s %(name)s request_id=%(request_id)s task_id=%(task_id)s service_path=%(service_path)s - %(message)s"
    ))

    root.handlers.clear()
    root.addHandler(handler)
    setattr(root, "_automana_configured", True)
