"""
Services panel — browse registered services, fill kwargs, run them, view output.

Layout
------
  ┌─ ServiceTree ──┬─ Detail ──────────────────────────────┐
  │  ▶ analytics   │  service: staging.scryfall.start...   │
  │  ▼ staging     │                                       │
  │    ▶ scryfall  │  [KwargForm inputs]                   │
  │  ▶ ops         │                                       │
  │                │  DB user: [Select ▼]  [ Run ↵ ]      │
  ├────────────────┴───────────────────────────────────────┤
  │  JsonViewer (output + call history)                    │
  └────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static
from textual.widgets.tree import TreeNode

from automana.tools.tui.widgets.db_user_select import DbUserSelect
from automana.tools.tui.widgets.json_viewer import JsonViewer
from automana.tools.tui.widgets.kwarg_form import KwargForm
from automana.tools.tui.widgets.service_tree import ServiceTree


class ServicesPanel(Vertical):
    """Full-height panel combining service browser, form, and output."""

    DEFAULT_CSS = """
    ServicesPanel {
        height: 1fr;
    }
    #top-row {
        height: 2fr;
    }
    #left-col {
        width: 30;
        min-width: 24;
    }
    #right-col {
        width: 1fr;
        padding: 0 1;
    }
    #service-label {
        color: $accent;
        margin-bottom: 1;
        text-style: bold;
    }
    #bottom-row {
        height: 1fr;
        padding: 0 1;
    }
    #action-row {
        height: auto;
        align: right middle;
        padding: 1 0;
    }
    #run-btn {
        min-width: 12;
    }
    #history-label {
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [("ctrl+r", "run_service", "Run")]

    def __init__(self, pool: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pool = pool
        self._selected_service: str | None = None
        self._history: deque[str] = deque(maxlen=10)

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-row"):
            with Vertical(id="left-col"):
                yield ServiceTree("Services", id="service-tree")
            with Vertical(id="right-col"):
                yield Static("(no service selected)", id="service-label")
                yield KwargForm(id="kwarg-form")
                with Horizontal(id="action-row"):
                    yield DbUserSelect(id="db-user-select")
                    yield Button("Run  ↵", id="run-btn", variant="primary")
        with Vertical(id="bottom-row"):
            yield Label("Output", id="history-label")
            yield JsonViewer(id="json-viewer", highlight=True, markup=True)

    def on_mount(self) -> None:
        self.run_worker(self._load_services(), exclusive=True)

    async def _load_services(self) -> None:
        viewer: JsonViewer = self.query_one("#json-viewer", JsonViewer)
        viewer.show_info("Loading services...")
        try:
            from automana.core.service_registry import ServiceRegistry
            keys = sorted(ServiceRegistry.list_services())
            tree: ServiceTree = self.query_one("#service-tree", ServiceTree)
            tree.populate(keys)
            viewer.show_info(f"{len(keys)} services loaded. Select one from the tree.")
        except Exception as exc:
            viewer.show_error(str(exc))

    async def on_tree_node_selected(self, event: ServiceTree.NodeSelected) -> None:
        node: TreeNode = event.node
        if node.data:  # leaf nodes carry the full service key
            self._selected_service = node.data
            label: Static = self.query_one("#service-label", Static)
            label.update(f"[bold]{node.data}[/bold]")
            form: KwargForm = self.query_one("#kwarg-form", KwargForm)
            await form.load_service(node.data)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self.run_worker(self._execute(), exclusive=False)

    def action_run_service(self) -> None:
        self.run_worker(self._execute(), exclusive=False)

    async def _execute(self) -> None:
        viewer: JsonViewer = self.query_one("#json-viewer", JsonViewer)
        if not self._selected_service:
            viewer.show_error("No service selected.")
            return

        form: KwargForm = self.query_one("#kwarg-form", KwargForm)
        db_select: DbUserSelect = self.query_one("#db-user-select", DbUserSelect)

        kwargs = form.get_kwargs()
        db_user = db_select.value if db_select.value else "app_backend"

        viewer.show_info(f"Running {self._selected_service} …")

        try:
            # Re-bootstrap only if the DB user changed from the pool's user
            from automana.core.service_manager import ServiceManager
            t0 = time.perf_counter()
            result = await ServiceManager.execute_service(self._selected_service, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000

            self._history.appendleft(
                f"{self._selected_service}({', '.join(f'{k}={v!r}' for k, v in kwargs.items())})"
            )
            viewer.show_result(result, elapsed_ms=elapsed)
        except Exception as exc:
            import traceback
            viewer.show_error(traceback.format_exc())
