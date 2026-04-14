"""
DbUserSelect — a Select widget for switching the active DB user.
"""

from __future__ import annotations

from textual.widgets import Select

from automana.tools.tui.shared import DB_USERS

_OPTIONS = [(f"{user}  ({role})", user) for user, (role, _, _) in DB_USERS.items()]


class DbUserSelect(Select[str]):
    """Drop-down that lists every configured DB user."""

    DEFAULT_CSS = """
    DbUserSelect {
        width: 1fr;
        margin-bottom: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            options=_OPTIONS,
            value="app_backend",
            prompt="DB user",
            **kwargs,
        )
