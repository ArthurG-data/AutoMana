"""
KwargForm — a dynamic input form built from a service's signature.

When a service key is selected, the form inspects the function's signature
via the ServiceRegistry and renders one Input row per parameter.
"""

from __future__ import annotations

import inspect
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, Static

from automana.tools.tui.shared import coerce


class KwargForm(Vertical):
    """Dynamic form that renders one labelled Input per service parameter."""

    DEFAULT_CSS = """
    KwargForm {
        height: auto;
        padding: 1 2;
        border: solid $accent-darken-2;
    }
    KwargForm Label {
        color: $text-muted;
        width: 22;
    }
    KwargForm Input {
        width: 1fr;
        margin-bottom: 1;
    }
    KwargForm #no-params {
        color: $text-muted;
        padding: 1 0;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._params: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("Select a service to build the form.", id="no-params")

    async def load_service(self, service_key: str) -> None:
        """Inspect the service function and rebuild the form inputs."""
        self._params = []
        await self.query("*").remove()

        try:
            import importlib
            from automana.core.service_registry import ServiceRegistry

            config = ServiceRegistry.get(service_key)
            if config is None:
                raise ValueError(f"Unknown service: {service_key}")

            module = importlib.import_module(config.module)
            fn = getattr(module, config.function)

            # Names that ServiceManager injects — don't render inputs for them.
            injected = {f"{n}_repository" for n in config.db_repositories}
            injected |= {f"{n}_repository" for n in config.api_repositories}
            if config.storage_services:
                injected.add("storage_service")
                injected |= {
                    f"{n}_storage_service" for n in config.storage_services[1:]
                }

            sig = inspect.signature(fn)
            params = [
                name for name, p in sig.parameters.items()
                if p.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                )
                and name not in ("self", "context")
                and name not in injected
            ]
        except Exception as exc:
            await self.mount(
                Static(f"(failed to introspect: {exc})", id="no-params")
            )
            return

        if not params:
            await self.mount(Static("(no parameters)", id="no-params"))
            return

        widgets = []
        for name in params:
            self._params.append(name)
            widgets.append(Label(f"{name}:"))
            widgets.append(Input(placeholder=name, id=f"kwarg_{name}"))
        await self.mount(*widgets)

    def get_kwargs(self) -> dict[str, Any]:
        """Return the current form values as a coerced kwargs dict."""
        result: dict[str, Any] = {}
        for name in self._params:
            widget = self.query_one(f"#kwarg_{name}", Input)
            raw = widget.value.strip()
            if raw:
                result[name] = coerce(raw)
        return result

    def clear_form(self) -> None:
        """Reset all inputs to empty."""
        for name in self._params:
            try:
                self.query_one(f"#kwarg_{name}", Input).value = ""
            except Exception:
                pass
