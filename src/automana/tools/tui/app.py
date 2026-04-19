"""
automana-tui — Terminal UI for AutoMana service testing.

Three tabs:
  1. Services  — browse and run any registered service (mirrors automana-run)
  2. Celery    — launch pipeline tasks and watch live status
  3. API       — test FastAPI endpoints via OpenAPI introspection

Usage
-----
    automana-tui

Run from the project root with the venv activated.  PostgreSQL must be
reachable (start with `docker compose ... up -d postgres`).
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from automana.tools.tui.panels.api import ApiPanel
from automana.tools.tui.panels.celery import CeleryPanel
from automana.tools.tui.panels.services import ServicesPanel
from automana.tools.tui.shared import bootstrap, teardown


class AutoManaTUI(App):
    """AutoMana TUI application."""

    TITLE = "AutoMana TUI"
    SUB_TITLE = "Service runner · Celery launcher · API tester"
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
    ]

    def __init__(self, pool: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pool = pool

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="services"):
            with TabPane("1 · Services", id="services"):
                yield ServicesPanel(pool=self._pool, id="services-panel")
            with TabPane("2 · Celery", id="celery"):
                yield CeleryPanel(id="celery-panel")
            with TabPane("3 · API", id="api"):
                yield ApiPanel(id="api-panel")
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    async def on_unmount(self) -> None:
        await teardown(self._pool)


def main() -> None:
    """Entry point registered as `automana-tui` in pyproject.toml."""
    import asyncio
    from automana.core.logging_config import configure_logging
    configure_logging()

    async def _run() -> None:
        pool = await bootstrap()
        app = AutoManaTUI(pool=pool)
        await app.run_async()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
