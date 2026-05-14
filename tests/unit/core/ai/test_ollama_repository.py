import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from automana.core.repositories.ai.ollama_repository import OllamaAPIRepository


@pytest.mark.asyncio
async def test_chat_completion_no_tools():
    repo = OllamaAPIRepository(base_url="http://localhost:11434")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}]
    }
    with patch.object(repo, "send", new=AsyncMock(return_value=mock_response)):
        result = await repo.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
        )
    assert result["choices"][0]["message"]["content"] == "hello"


@pytest.mark.asyncio
async def test_chat_completion_with_tools():
    repo = OllamaAPIRepository(base_url="http://localhost:11434")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "search_cards", "arguments": '{"query": "bolt"}'}}
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    with patch.object(repo, "send", new=AsyncMock(return_value=mock_response)):
        result = await repo.chat_completion(
            messages=[{"role": "user", "content": "find bolt"}],
            tools=[{"type": "function", "function": {"name": "search_cards"}}],
        )
    assert result["choices"][0]["finish_reason"] == "tool_calls"
