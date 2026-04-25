"""
Bridge between Python's logging framework and the Textual LogViewer widget.

A plain StreamHandler(sys.stdout) bleeds log lines into the middle of the
rendered TUI because Textual owns the terminal.  This handler captures the
record and dispatches it onto the Textual event loop via App.call_from_thread,
so logs surface cleanly inside the dedicated Logs tab.

Also provides a small BufferingHandler used during bootstrap — any log
records emitted before the App mounts are collected and flushed into the
LogViewer once it is ready.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import App

    from automana.tools.tui.widgets.log_viewer import LogViewer


class TextualLogHandler(logging.Handler):
    """Forward log records to a LogViewer widget via the Textual event loop."""

    def __init__(self, app: "App", viewer: "LogViewer") -> None:
        super().__init__()
        self._app = app
        self._viewer = viewer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._app.call_from_thread(self._viewer.append_record, record)
        except Exception:
            # Never let a logging failure crash the TUI or the calling thread.
            pass


class BufferingLogHandler(logging.Handler):
    """Collect records until the TUI is ready, then flush via `drain_to`."""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self._records: list[logging.LogRecord] = []
        self._capacity = capacity

    def emit(self, record: logging.LogRecord) -> None:
        if len(self._records) >= self._capacity:
            self._records.pop(0)
        self._records.append(record)

    def drain_to(self, viewer: "LogViewer") -> None:
        for record in self._records:
            viewer.append_record(record)
        self._records.clear()
