"""
automana-tui — Terminal UI for AutoMana service testing.

Four tabs:
  1. Services  — browse and run any registered service (mirrors automana-run)
  2. Celery    — launch pipeline tasks and watch live status
  3. API       — test FastAPI endpoints via OpenAPI introspection
  4. Logs      — live feed of Python logging output (captured, not stdout)

Usage
-----
    automana-tui

Run from the project root with the venv activated.  PostgreSQL must be
reachable (start with `docker compose ... up -d postgres`).
"""

from __future__ import annotations

import logging
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from automana.tools.tui.log_handler import BufferingLogHandler, TextualLogHandler
from automana.tools.tui.panels.api import ApiPanel
from automana.tools.tui.panels.celery import CeleryPanel
from automana.tools.tui.panels.services import ServicesPanel
from automana.tools.tui.shared import bootstrap, teardown
from automana.tools.tui.widgets.log_viewer import LogViewer


class AutoManaTUI(App):
    """AutoMana TUI application."""

    TITLE = "AutoMana TUI"
    SUB_TITLE = "Service runner · Celery launcher · API tester · Logs"
    CSS = """
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("1", "switch_tab('services')", "Services"),
        Binding("2", "switch_tab('celery')", "Celery"),
        Binding("3", "switch_tab('api')", "API"),
        Binding("4", "switch_tab('logs')", "Logs"),
        Binding("ctrl+l", "clear_logs", "Clear logs"),
    ]

    def __init__(self, pool: Any, buffer_handler: BufferingLogHandler | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pool = pool
        self._buffer_handler = buffer_handler

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="services"):
            with TabPane("1 · Services", id="services"):
                yield ServicesPanel(pool=self._pool, id="services-panel")
            with TabPane("2 · Celery", id="celery"):
                yield CeleryPanel(id="celery-panel")
            with TabPane("3 · API", id="api"):
                yield ApiPanel(id="api-panel")
            with TabPane("4 · Logs", id="logs"):
                yield LogViewer(id="log-viewer")
        yield Footer()

    def on_mount(self) -> None:
        self._wire_logging()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_clear_logs(self) -> None:
        self.query_one("#log-viewer", LogViewer).clear_logs()

    async def on_unmount(self) -> None:
        await teardown(self._pool)

    def _wire_logging(self) -> None:
        """Route root-logger output into the Logs tab and silence stdout."""
        viewer: LogViewer = self.query_one("#log-viewer", LogViewer)
        root = logging.getLogger()

        # Drop any handler that writes to stdout/stderr — those bleed into the TUI.
        import sys
        for h in list(root.handlers):
            stream = getattr(h, "stream", None)
            if stream in (sys.stdout, sys.stderr):
                root.removeHandler(h)

        # Flush anything captured before mount, then detach the buffer.
        if self._buffer_handler is not None:
            self._buffer_handler.drain_to(viewer)
            root.removeHandler(self._buffer_handler)
            self._buffer_handler = None

        handler = TextualLogHandler(self, viewer)
        handler.setLevel(root.level or logging.INFO)
        root.addHandler(handler)


def main() -> None:
    """Entry point registered as `automana-tui` in pyproject.toml."""
    import asyncio
    import os

    # Bootstrap logs (DB pool init, etc.) must NOT hit stdout — the TUI will
    # repaint over them.  Buffer until the LogViewer is mounted.
    root = logging.getLogger()
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    buffer_handler = BufferingLogHandler()
    root.addHandler(buffer_handler)
    setattr(root, "_automana_configured", True)

    async def _run() -> None:
        pool = await bootstrap()
        app = AutoManaTUI(pool=pool, buffer_handler=buffer_handler)
        await app.run_async()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
