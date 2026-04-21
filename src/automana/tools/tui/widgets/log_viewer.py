"""
LogViewer — RichLog widget that renders Python log records with colored
level tags.  Consumed by TextualLogHandler (see tools/tui/log_handler.py)
to keep log output inside the TUI instead of leaking to stdout.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from rich.text import Text
from textual.widgets import RichLog

_LEVEL_STYLES: dict[str, str] = {
    "DEBUG":    "dim",
    "INFO":     "cyan",
    "WARNING":  "yellow",
    "ERROR":    "bold red",
    "CRITICAL": "bold white on red",
}

# Matches ANSI CSI/OSC escape sequences that libraries (Celery, SQLAlchemy,
# colorlog, etc.) embed in log messages.  Stripping them prevents the raw
# \x1b[... codes from rendering as gibberish in the TUI.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


def _sanitize(text: str) -> str:
    """Strip ANSI escapes and control chars that render as glyph soup."""
    text = _ANSI_ESCAPE_RE.sub("", text)
    # Replace bare carriage returns and keep only printable/whitespace chars.
    cleaned_chars = []
    for ch in text:
        if ch in ("\n", "\t"):
            cleaned_chars.append(ch)
        elif ch == "\r":
            continue
        elif ord(ch) < 32:
            cleaned_chars.append("?")
        else:
            cleaned_chars.append(ch)
    return "".join(cleaned_chars)


class LogViewer(RichLog):
    """Scrollable panel displaying log records with colored level tags."""

    DEFAULT_CSS = """
    LogViewer {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    """

    def __init__(self, *args, max_lines: int = 2000, **kwargs) -> None:
        super().__init__(*args, max_lines=max_lines, **kwargs)

    def append_record(self, record: logging.LogRecord) -> None:
        """Render a single LogRecord as a styled line."""
        style = _LEVEL_STYLES.get(record.levelname, "white")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        try:
            message = record.getMessage()
        except Exception as exc:
            message = f"<unformattable log record: {exc!r}>"
        message = _sanitize(message)

        # Text.append bypasses Rich markup parsing, so brackets in log
        # messages (e.g. "[INFO]") render literally instead of being
        # interpreted as style tags.
        line = Text()
        line.append(f"{ts} ", style="dim")
        line.append(f"{record.levelname:<8}", style=style)
        line.append(f" {record.name} ", style="dim magenta")
        line.append(message)

        extras: list[str] = []
        for key in ("request_id", "task_id", "service_path"):
            value = getattr(record, key, None)
            if value:
                extras.append(f"{key}={value}")
        if extras:
            line.append(f"  ({', '.join(extras)})", style="dim")

        self.write(line)

        if record.exc_info:
            exc_text = _sanitize(logging.Formatter().formatException(record.exc_info))
            self.write(Text(exc_text, style="red"))

    def clear_logs(self) -> None:
        """Wipe the current log buffer."""
        self.clear()
