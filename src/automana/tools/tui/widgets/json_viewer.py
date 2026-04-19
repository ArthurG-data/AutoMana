"""
JsonViewer — a RichLog panel that pretty-prints JSON with syntax highlighting.
"""

from __future__ import annotations

import json
from typing import Any

from rich.syntax import Syntax
from textual.widgets import RichLog


class JsonViewer(RichLog):
    """Scrollable log panel with JSON syntax highlighting."""

    DEFAULT_CSS = """
    JsonViewer {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    """

    def show_result(self, result: Any, elapsed_ms: float | None = None) -> None:
        """Render a service result as highlighted JSON."""
        self.clear()
        if elapsed_ms is not None:
            self.write(f"[dim]elapsed: {elapsed_ms:.1f} ms[/dim]\n")
        try:
            text = json.dumps(result, indent=2, default=str)
        except Exception:
            text = repr(result)
        self.write(Syntax(text, "json", theme="monokai", word_wrap=True))

    def show_error(self, message: str) -> None:
        """Render an error message in red."""
        self.clear()
        self.write(f"[bold red]ERROR[/bold red]\n{message}")

    def show_info(self, message: str) -> None:
        """Render a plain info line."""
        self.write(f"[dim]{message}[/dim]")
