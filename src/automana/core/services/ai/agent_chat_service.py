from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

import asyncpg
from redis.asyncio import Redis
from redis.exceptions import RedisError

from automana.core.repositories.ai.ollama_repository import OllamaAPIRepository
from automana.core.services.ai.agent_tools import TOOL_MAP, TOOL_SCHEMAS
from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_HISTORY_KEY = "ai:chat:{user_id}:{session_id}"
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _history_key(user_id: str, session_id: str) -> str:
    return _HISTORY_KEY.format(user_id=user_id, session_id=session_id)


async def _load_history(redis: Redis, key: str, window: int) -> list[dict]:
    try:
        raw = await redis.get(key)
        if not raw:
            return []
        history: list[dict] = json.loads(raw)
        return history[-window:]
    except RedisError as e:
        logger.warning("agent_history_load_error", extra={"key": key, "error": str(e)})
        return []


async def _save_history(redis: Redis, key: str, history: list[dict], ttl: int) -> None:
    try:
        await redis.setex(key, ttl, json.dumps(history))
    except RedisError as e:
        logger.warning("agent_history_save_error", extra={"key": key, "error": str(e)})


async def run_agent_turn(
    *,
    conn: asyncpg.Connection,
    redis: Redis,
    ollama_repo: OllamaAPIRepository,
    user_id: str,
    session_id: str,
    message: str,
    app_code: str | None = None,
) -> dict[str, Any]:
    """Execute one user turn: load history, call Ollama, dispatch tools, return reply."""
    settings = get_settings()
    key = _history_key(user_id, session_id)
    history = await _load_history(redis, key, settings.agent_chat_window)

    history.append({"role": "user", "content": message})

    tools_called: list[str] = []

    # First Ollama pass — tools enabled (snapshot history so call_args is stable)
    response = await ollama_repo.chat_completion(
        messages=list(history),
        tools=TOOL_SCHEMAS,
    )
    choice = response["choices"][0]
    assistant_msg: dict = choice["message"]

    if choice.get("finish_reason") == "tool_calls" and assistant_msg.get("tool_calls"):
        tool_messages: list[dict] = []

        for tc in assistant_msg["tool_calls"]:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            # Always inject server-controlled values — never trust LLM-supplied identity args
            if fn_name == "get_collection_summary":
                args["user_id"] = user_id
            if fn_name in ("get_active_listings", "get_sold_orders") and app_code is not None:
                args["app_code"] = app_code

            callable_fn = TOOL_MAP.get(fn_name)
            if callable_fn is None:
                logger.warning("agent_unknown_tool", extra={"tool": fn_name})
                continue

            try:
                tool_result = await callable_fn(conn, **args)
                tools_called.append(fn_name)
            except Exception as e:
                logger.error(
                    "agent_tool_error",
                    extra={"tool": fn_name, "error": str(e)},
                    exc_info=True,
                )
                tool_result = json.dumps({"error": "Error retrieving data"})

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })

        # Second pass — no tools to prevent looping
        second_history = history + [assistant_msg] + tool_messages
        second_response = await ollama_repo.chat_completion(
            messages=second_history,
            tools=None,
        )
        second_choice = second_response["choices"][0]
        final_content = _THINK_RE.sub("", second_choice["message"].get("content") or "").strip()
    else:
        final_content = _THINK_RE.sub("", assistant_msg.get("content") or "").strip()

    if not final_content:
        final_content = "I couldn't generate a response. Please try again."

    history.append({"role": "assistant", "content": final_content})
    await _save_history(redis, key, history, settings.agent_chat_ttl)

    return {
        "reply": final_content,
        "session_id": session_id,
        "tools_called": tools_called,
    }
