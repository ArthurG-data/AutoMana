"""
Celery panel — launch pipeline tasks and poll their live status.

Layout
------
  ┌─ Task list ─────────────┬─ Pipeline steps ──────────────┐
  │  daily_scryfall_data_.. │  Step 1: start_pipeline       │
  │  daily_mtgjson_data_..  │  Step 2: get_bulk_data_uri    │
  │  mtgStock_download_..   │  ...                          │
  │                         │  [ Launch ]                   │
  ├─────────────────────────┴───────────────────────────────┤
  │  Live status / output (JsonViewer)                      │
  └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, ListItem, ListView, Static

from automana.tools.tui.widgets.json_viewer import JsonViewer

# ---------------------------------------------------------------------------
# Static task definitions (mirrors worker/tasks/pipelines.py)
# ---------------------------------------------------------------------------

@dataclass
class CeleryTask:
    name: str          # Celery task name as registered
    label: str         # Human-readable label
    steps: list[str]   # Ordered service keys in the chain


KNOWN_TASKS: list[CeleryTask] = [
    CeleryTask(
        name="daily_scryfall_data_pipeline",
        label="Scryfall daily pipeline",
        steps=[
            "staging.scryfall.start_pipeline",
            "staging.scryfall.get_bulk_data_uri",
            "staging.scryfall.download_bulk_manifests",
            "staging.scryfall.update_data_uri_in_ops_repository",
            "staging.scryfall.download_sets",
            "card_catalog.set.process_large_sets_json",
            "staging.scryfall.download_cards_bulk",
            "card_catalog.card.process_large_json",
            "ops.pipeline_services.finish_run",
            "staging.scryfall.delete_old_scryfall_folders",
            "ops.integrity.scryfall_run_diff",
            "ops.integrity.scryfall_integrity",
            "ops.integrity.public_schema_leak",
        ],
    ),
    CeleryTask(
        name="run_scryfall_integrity_checks",
        label="Scryfall integrity checks (parallel)",
        steps=[
            "ops.integrity.scryfall_run_diff",
            "ops.integrity.scryfall_integrity",
            "ops.integrity.public_schema_leak",
        ],
    ),
    CeleryTask(
        name="daily_mtgjson_data_pipeline",
        label="MTGJson daily pipeline",
        steps=[
            "ops.pipeline_services.start_run",
            "mtgjson.data.download.today",
            "staging.mtgjson.stream_to_staging",
            "staging.mtgjson.promote_to_price_observation",
            "staging.mtgjson.cleanup_raw_files",
            "ops.pipeline_services.finish_run",
        ],
    ),
    CeleryTask(
        name="mtgStock_download_pipeline",
        label="MTGStock download pipeline",
        steps=[
            "ops.pipeline_services.start_run",
            "mtg_stock.data_staging.bulk_load",
            "mtg_stock.data_staging.from_raw_to_staging",
            "mtg_stock.data_staging.from_staging_to_dim",
            "mtg_stock.data_staging.from_dim_to_prices",
            "ops.pipeline_services.finish_run",
        ],
    ),
]

_CELERY_APP = "automana.worker.main:app"
_CELERY_CMD = ["celery", "-A", _CELERY_APP]


class CeleryPanel(Vertical):
    """Panel for launching Celery pipeline tasks and watching their status."""

    DEFAULT_CSS = """
    CeleryPanel {
        height: 1fr;
    }
    #top-row {
        height: 2fr;
    }
    #task-list-col {
        width: 35;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    #steps-col {
        width: 1fr;
        padding: 0 1;
    }
    #steps-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #step-table {
        height: 1fr;
    }
    #launch-row {
        height: auto;
        align: right middle;
        padding: 1 0;
    }
    #launch-btn {
        min-width: 14;
    }
    #bottom-row {
        height: 1fr;
        padding: 0 1;
    }
    #status-label {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._selected_task: CeleryTask | None = None
        self._polling = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-row"):
            with Vertical(id="task-list-col"):
                yield Label("Pipeline Tasks")
                yield ListView(
                    *[ListItem(Static(t.label), id=f"task_{i}") for i, t in enumerate(KNOWN_TASKS)],
                    id="task-listview",
                )
            with Vertical(id="steps-col"):
                yield Static("(select a task)", id="steps-title")
                yield DataTable(id="step-table", show_header=True, cursor_type="none")
                with Horizontal(id="launch-row"):
                    yield Button("Launch", id="launch-btn", variant="primary")
        with Vertical(id="bottom-row"):
            yield Label("Output / Status", id="status-label")
            yield JsonViewer(id="celery-output", highlight=True, markup=True)

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#step-table", DataTable)
        table.add_columns("#", "Service key")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("_")[1])
        self._selected_task = KNOWN_TASKS[idx]
        self._refresh_steps()

    def _refresh_steps(self) -> None:
        if not self._selected_task:
            return
        title: Static = self.query_one("#steps-title", Static)
        title.update(f"[bold]{self._selected_task.label}[/bold]")
        table: DataTable = self.query_one("#step-table", DataTable)
        table.clear()
        for i, step in enumerate(self._selected_task.steps, 1):
            table.add_row(str(i), step)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "launch-btn":
            self.run_worker(self._launch(), exclusive=False)

    async def _launch(self) -> None:
        viewer: JsonViewer = self.query_one("#celery-output", JsonViewer)
        if not self._selected_task:
            viewer.show_error("No task selected.")
            return

        task_name = self._selected_task.name
        viewer.show_info(f"Launching {task_name} …")

        try:
            cmd = _CELERY_CMD + ["call", task_name]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                viewer.show_error(stderr.decode().strip() or "celery call failed")
                return

            task_id = stdout.decode().strip()
            viewer.show_info(f"Task ID: [bold]{task_id}[/bold]")
            self.run_worker(self._poll_status(task_id), exclusive=False)

        except FileNotFoundError:
            viewer.show_error(
                "celery command not found. Make sure the venv is activated "
                "and the Celery worker is accessible."
            )
        except Exception as exc:
            import traceback as tb
            viewer.show_error(tb.format_exc())

    async def _poll_status(self, task_id: str) -> None:
        """Poll celery inspect active every 3 s until the task disappears."""
        viewer: JsonViewer = self.query_one("#celery-output", JsonViewer)
        for _ in range(40):  # max ~2 min of polling
            await asyncio.sleep(3)
            try:
                cmd = _CELERY_CMD + ["inspect", "active", "--json"]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                raw = stdout.decode().strip()
                if not raw:
                    continue
                data = json.loads(raw)
                # Flatten all workers' active lists
                all_active = [t for tasks in data.values() for t in tasks]
                running = [t for t in all_active if t.get("id") == task_id]
                if running:
                    viewer.show_result(running[0])
                else:
                    viewer.show_info(f"Task [bold]{task_id}[/bold] no longer active (completed or failed).")
                    return
            except Exception:
                pass
