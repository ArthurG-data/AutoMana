from __future__ import annotations

import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_ollama_response(content: str | None = "Hello!", tool_calls: list | None = None):
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "choices": [
            {"message": msg, "finish_reason": "tool_calls" if tool_calls else "stop"}
        ]
    }


@pytest.mark.asyncio
async def test_run_agent_turn_no_tools():
    """Simple reply with no tool calls."""
    from automana.core.services.ai.agent_chat_service import run_agent_turn

    ollama_repo = AsyncMock()
    ollama_repo.chat_completion = AsyncMock(return_value=_make_ollama_response("Nice card!"))

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()

    conn = AsyncMock()

    result = await run_agent_turn(
        conn=conn,
        redis=redis,
        ollama_repo=ollama_repo,
        user_id="user-1",
        session_id="sess-1",
        message="What is Lightning Bolt?",
    )

    assert result["reply"] == "Nice card!"
    assert result["tools_called"] == []
    assert result["session_id"] == "sess-1"
    ollama_repo.chat_completion.assert_called_once()


@pytest.mark.asyncio
async def test_run_agent_turn_with_tool_call():
    """Tool call triggers second Ollama pass."""
    from automana.core.services.ai.agent_chat_service import run_agent_turn
    from automana.core.services.ai.agent_tools import TOOL_MAP

    tool_calls = [
        {
            "id": "call_abc",
            "function": {
                "name": "search_cards",
                "arguments": json.dumps({"query": "bolt"}),
            },
        }
    ]

    ollama_repo = AsyncMock()
    ollama_repo.chat_completion = AsyncMock(
        side_effect=[
            _make_ollama_response(None, tool_calls=tool_calls),
            _make_ollama_response("Found 1 card."),
        ]
    )

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()

    conn = AsyncMock()

    with patch.dict(
        TOOL_MAP,
        {"search_cards": AsyncMock(return_value=json.dumps([{"card_name": "Lightning Bolt"}]))},
    ):
        result = await run_agent_turn(
            conn=conn,
            redis=redis,
            ollama_repo=ollama_repo,
            user_id="user-1",
            session_id="sess-2",
            message="Find bolt",
        )

    assert result["reply"] == "Found 1 card."
    assert "search_cards" in result["tools_called"]
    assert ollama_repo.chat_completion.call_count == 2


@pytest.mark.asyncio
async def test_run_agent_turn_history_window():
    """History is sliced to agent_chat_window messages."""
    from automana.core.services.ai.agent_chat_service import run_agent_turn

    # 12 messages in cache (> window of 10)
    old_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(12)
    ]

    ollama_repo = AsyncMock()
    ollama_repo.chat_completion = AsyncMock(return_value=_make_ollama_response("ok"))

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps(old_history).encode())
    redis.setex = AsyncMock()

    conn = AsyncMock()

    await run_agent_turn(
        conn=conn,
        redis=redis,
        ollama_repo=ollama_repo,
        user_id="u",
        session_id="s",
        message="new message",
    )

    call_kwargs = ollama_repo.chat_completion.call_args
    messages_sent = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][0]
    # window=10, plus the new user message = 11 total (10 from history + 1 new)
    assert len(messages_sent) <= 11


@pytest.mark.asyncio
async def test_run_agent_turn_redis_unavailable():
    """Redis failure falls back to empty history — no exception raised."""
    from automana.core.services.ai.agent_chat_service import run_agent_turn
    from redis.exceptions import RedisError

    ollama_repo = AsyncMock()
    ollama_repo.chat_completion = AsyncMock(return_value=_make_ollama_response("ok"))

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=RedisError("timeout"))
    redis.setex = AsyncMock(side_effect=RedisError("timeout"))

    conn = AsyncMock()

    result = await run_agent_turn(
        conn=conn,
        redis=redis,
        ollama_repo=ollama_repo,
        user_id="u",
        session_id="s",
        message="hello",
    )

    assert result["reply"] == "ok"


@pytest.mark.asyncio
async def test_run_agent_turn_tool_error_continues():
    """A failing tool logs the error and returns a placeholder, does not raise."""
    from automana.core.services.ai.agent_chat_service import run_agent_turn
    from automana.core.services.ai.agent_tools import TOOL_MAP

    tool_calls = [{"id": "c1", "function": {"name": "search_cards", "arguments": "{}"}}]

    ollama_repo = AsyncMock()
    ollama_repo.chat_completion = AsyncMock(
        side_effect=[
            _make_ollama_response(None, tool_calls=tool_calls),
            _make_ollama_response("ok"),
        ]
    )

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()

    conn = AsyncMock()

    with patch.dict(TOOL_MAP, {"search_cards": AsyncMock(side_effect=Exception("DB down"))}):
        result = await run_agent_turn(
            conn=conn,
            redis=redis,
            ollama_repo=ollama_repo,
            user_id="u",
            session_id="s",
            message="find cards",
        )

    assert result["reply"] == "ok"
