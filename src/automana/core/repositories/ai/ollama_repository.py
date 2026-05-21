from __future__ import annotations

import logging
from typing import Any

from automana.core.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient

logger = logging.getLogger(__name__)


class OllamaAPIRepository(BaseApiClient):
    """HTTP client for Ollama's OpenAI-compatible chat completions endpoint."""

    def __init__(self, base_url: str = "http://ollama:11434", timeout: float = 120.0):
        self._base_url = base_url.rstrip("/")
        super().__init__(timeout=timeout)

    @property
    def name(self) -> str:
        return "OllamaAPIRepository"

    def _get_base_url(self) -> str:
        return self._base_url

    def default_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    async def chat_completion(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> dict[str, Any]:
        """POST /v1/chat/completions — returns raw response dict."""
        from automana.core.settings import get_settings
        _model = model or get_settings().ollama_model
        payload: dict[str, Any] = {
            "model": _model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        logger.info(
            "ollama_chat_request",
            extra={"model": _model, "msg_count": len(messages), "tools": len(tools or [])},
        )
        response = await self.send("POST", "/v1/chat/completions", json=payload)
        return response.json()
