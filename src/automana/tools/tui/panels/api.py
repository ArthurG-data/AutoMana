"""
API panel — test FastAPI endpoints via /openapi.json introspection.

Layout
------
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
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

import httpx
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static, Tree
from textual.widgets.tree import TreeNode

from automana.tools.tui.shared import coerce
from automana.tools.tui.widgets.json_viewer import JsonViewer

_DEFAULT_BASE_URL = "http://localhost:8000"
_METHOD_COLORS = {
    "get":    "green",
    "post":   "blue",
    "put":    "yellow",
    "patch":  "orange",
    "delete": "red",
}


class ApiPanel(Vertical):
    """Panel for browsing and executing FastAPI endpoints."""

    DEFAULT_CSS = """
    ApiPanel {
        height: 1fr;
    }
    #top-row {
        height: 2fr;
    }
    #route-col {
        width: 35;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    #form-col {
        width: 1fr;
        padding: 0 1;
    }
    #endpoint-label {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #base-url-input {
        margin-bottom: 1;
    }
    #bearer-input {
        margin-bottom: 1;
    }
    #params-area {
        height: auto;
    }
    #send-row {
        height: auto;
        align: right middle;
        padding: 1 0;
    }
    #send-btn {
        min-width: 10;
    }
    #bottom-row {
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._selected: dict[str, Any] | None = None  # OpenAPI operation dict
        self._selected_method: str = "get"
        self._selected_path: str = ""
        self._param_names: list[str] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-row"):
            with Vertical(id="route-col"):
                yield Tree("Routes", id="route-tree")
            with Vertical(id="form-col"):
                yield Static("(select a route)", id="endpoint-label")
                yield Label("Base URL")
                yield Input(value=_DEFAULT_BASE_URL, id="base-url-input")
                yield Label("Bearer token (optional)")
                yield Input(placeholder="eyJ...", password=True, id="bearer-input")
                yield Vertical(id="params-area")
                with Horizontal(id="send-row"):
                    yield Button("Send", id="send-btn", variant="primary")
        with Vertical(id="bottom-row"):
            yield Label("Response")
            yield JsonViewer(id="api-output", highlight=True, markup=True)

    def on_mount(self) -> None:
        self.run_worker(self._load_routes(), exclusive=True)

    async def _load_routes(self) -> None:
        viewer: JsonViewer = self.query_one("#api-output", JsonViewer)
        base_url: str = self.query_one("#base-url-input", Input).value.rstrip("/")
        viewer.show_info(f"Fetching {base_url}/openapi.json …")

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{base_url}/openapi.json")
                resp.raise_for_status()
                spec: dict = resp.json()
        except Exception as exc:
            viewer.show_error(
                f"Could not fetch OpenAPI spec from {base_url}.\n"
                f"Make sure the API server is running.\n\n{exc}"
            )
            return

        tree: Tree = self.query_one("#route-tree", Tree)
        tree.clear()

        # Group routes by first path segment
        groups: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)
        for path, methods in spec.get("paths", {}).items():
            segment = path.strip("/").split("/")[0] or "root"
            for method, operation in methods.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    groups[segment].append((method.upper(), path, operation))

        for segment, routes in sorted(groups.items()):
            branch = tree.root.add(segment, expand=False)
            for method, path, operation in sorted(routes, key=lambda x: x[1]):
                color = _METHOD_COLORS.get(method.lower(), "white")
                label = f"[{color}]{method}[/{color}] {path}"
                branch.add_leaf(label, data={"method": method.lower(), "path": path, "op": operation})

        tree.root.expand()
        viewer.show_info(f"Loaded {sum(len(v) for v in groups.values())} endpoints.")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node: TreeNode = event.node
        if not node.data:
            return

        self._selected_method = node.data["method"]
        self._selected_path = node.data["path"]
        operation = node.data["op"]

        color = _METHOD_COLORS.get(self._selected_method, "white")
        label: Static = self.query_one("#endpoint-label", Static)
        label.update(
            f"[{color}]{self._selected_method.upper()}[/{color}] "
            f"[bold]{self._selected_path}[/bold]"
        )

        # Rebuild param inputs
        params_area: Vertical = self.query_one("#params-area", Vertical)
        params_area.remove_children()
        self._param_names = []

        parameters = operation.get("parameters", [])
        if parameters:
            params_area.mount(Label("[dim]Parameters:[/dim]"))
            for param in parameters:
                name = param["name"]
                self._param_names.append(name)
                params_area.mount(Label(f"  {name}:"))
                params_area.mount(Input(placeholder=name, id=f"apiparam_{name}"))

        # If POST/PUT/PATCH with a body, add a raw JSON body input
        if self._selected_method in ("post", "put", "patch"):
            self._param_names.append("__body__")
            params_area.mount(Label("[dim]Request body (JSON):[/dim]"))
            params_area.mount(Input(placeholder='{"key": "value"}', id="apiparam___body__"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self.run_worker(self._send(), exclusive=False)

    async def _send(self) -> None:
        viewer: JsonViewer = self.query_one("#api-output", JsonViewer)
        if not self._selected_path:
            viewer.show_error("No endpoint selected.")
            return

        base_url: str = self.query_one("#base-url-input", Input).value.rstrip("/")
        bearer: str = self.query_one("#bearer-input", Input).value.strip()

        # Collect params
        query_params: dict[str, Any] = {}
        body: Any = None
        for name in self._param_names:
            try:
                widget = self.query_one(f"#apiparam_{name}", Input)
                raw = widget.value.strip()
                if not raw:
                    continue
                if name == "__body__":
                    import json
                    body = json.loads(raw)
                else:
                    query_params[name] = coerce(raw)
            except Exception:
                pass

        headers: dict[str, str] = {}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        url = base_url + self._selected_path
        viewer.show_info(f"{self._selected_method.upper()} {url} …")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                t0 = time.perf_counter()
                resp = await client.request(
                    method=self._selected_method,
                    url=url,
                    params=query_params if self._selected_method == "get" else None,
                    json=body,
                    headers=headers,
                )
                elapsed = (time.perf_counter() - t0) * 1000

            status_color = "green" if resp.status_code < 400 else "red"
            viewer.show_info(
                f"[{status_color}]HTTP {resp.status_code}[/{status_color}]  "
                f"elapsed: {elapsed:.1f} ms"
            )
            try:
                viewer.show_result(resp.json(), elapsed_ms=elapsed)
            except Exception:
                viewer.show_info(resp.text[:2000])

        except Exception:
            import traceback
            viewer.show_error(traceback.format_exc())
