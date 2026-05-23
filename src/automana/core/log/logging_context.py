from __future__ import annotations

import contextvars
from typing import Optional

_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
_task_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("task_id", default=None)
_service_path: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("service_path", default=None)


def set_request_id(value: Optional[str]) -> None:
    _request_id_var.set(value)
def get_request_id() -> Optional[str]:
    return _request_id_var.get()

def set_task_id(value: Optional[str]) -> None:
    _task_id_var.set(value)
def get_task_id() -> Optional[str]:
    return _task_id_var.get()

def set_service_path(v: Optional[str]) -> None: _service_path.set(v)
def get_service_path() -> Optional[str]: return _service_path.get()