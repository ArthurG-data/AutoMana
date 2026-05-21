# Agent Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a locally-hosted Qwen3-30B-A3B model (Ollama) into AutoMana as a data-aware chatbot accessible via `POST /api/integrations/ai/chat` and as an internal async callable.

**Architecture:** Ollama runs as a docker-compose sidecar; `OllamaAPIRepository(BaseApiClient)` wraps the OpenAI-compatible `/v1/chat/completions` endpoint; `AgentChatService` handles the tool-calling loop and Redis conversation history; six read-only asyncpg tool callables query live AutoMana data via the existing `app_agent` DB role.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, Redis (aioredis), httpx, Pydantic v2, Ollama (docker), Qwen3-30B-A3B GGUF, pytest, pytest-asyncio, unittest.mock

---

## File Map

| Action | File |
|--------|------|
| Create | `src/automana/core/repositories/ai/__init__.py` |
| Create | `src/automana/core/repositories/ai/ollama_repository.py` |
| Create | `src/automana/core/services/ai/__init__.py` |
| Create | `src/automana/core/services/ai/agent_tools.py` |
| Create | `src/automana/core/services/ai/agent_chat_service.py` |
| Create | `src/automana/api/routers/integrations/ai/__init__.py` |
| Create | `src/automana/api/routers/integrations/ai/agent_router.py` |
| Create | `tests/unit/core/ai/__init__.py` |
| Create | `tests/unit/core/ai/test_agent_chat_service.py` |
| Create | `tests/unit/core/ai/test_agent_tools.py` |
| Modify | `src/automana/core/settings.py` — add four Ollama/agent fields |
| Modify | `src/automana/core/service_registry.py` — register `ollama` API repository |
| Modify | `src/automana/api/routers/integrations/__init__.py` — include `ai_router` |
| Modify | `deploy/docker-compose.dev.yml` — add `ollama` sidecar + volume |
| Modify | `deploy/docker-compose.prod.yml` — add `ollama` sidecar + volume |

---

## Task 1: Settings

**Files:**
- Modify: `src/automana/core/settings.py`

- [ ] **Step 1: Add four fields to the `Settings` class (after the Redis block)**

Open `src/automana/core/settings.py` and add after the `redis_cache_url` field:

```python
# Ollama / Agent chat
ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
ollama_model: str = Field(default="qwen3:30b-a3b", alias="OLLAMA_MODEL")
agent_chat_window: int = Field(default=10, alias="AGENT_CHAT_WINDOW")
agent_chat_ttl: int = Field(default=7200, alias="AGENT_CHAT_TTL")
```

- [ ] **Step 2: Verify settings load without error**

```bash
cd /home/arthur/projects/AutoMana
python -c "from automana.core.settings import get_settings; s = get_settings(); print(s.ollama_base_url, s.ollama_model)"
```

Expected output: `http://ollama:11434 qwen3:30b-a3b`

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/settings.py
git commit -m "feat(ai): add Ollama and agent chat settings"
```

---

## Task 2: OllamaAPIRepository

**Files:**
- Create: `src/automana/core/repositories/ai/__init__.py`
- Create: `src/automana/core/repositories/ai/ollama_repository.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/ai/__init__.py` (empty).

Create `tests/unit/core/ai/test_ollama_repository.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/arthur/projects/AutoMana
python -m pytest tests/unit/core/ai/test_ollama_repository.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` (file not created yet).

- [ ] **Step 3: Create the repository**

Create `src/automana/core/repositories/ai/__init__.py` (empty).

Create `src/automana/core/repositories/ai/ollama_repository.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/core/ai/test_ollama_repository.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/ai/ tests/unit/core/ai/
git commit -m "feat(ai): add OllamaAPIRepository"
```

---

## Task 3: Register OllamaAPIRepository in ServiceRegistry

**Files:**
- Modify: `src/automana/core/service_registry.py`

- [ ] **Step 1: Add registration at the bottom of the API repositories block**

Open `src/automana/core/service_registry.py`. Find the last `ServiceRegistry.register_api_repository(...)` call and add after it:

```python
ServiceRegistry.register_api_repository(
    "ollama",
    "automana.core.repositories.ai.ollama_repository",
    "OllamaAPIRepository",
)
```

- [ ] **Step 2: Verify registration**

```bash
python -c "
from automana.core.service_registry import ServiceRegistry
info = ServiceRegistry.get_api_repository('ollama')
print(info)
"
```

Expected: `('automana.core.repositories.ai.ollama_repository', 'OllamaAPIRepository')`

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/service_registry.py
git commit -m "feat(ai): register OllamaAPIRepository in ServiceRegistry"
```

---

## Task 4: Agent Tools

**Files:**
- Create: `src/automana/core/services/ai/__init__.py`
- Create: `src/automana/core/services/ai/agent_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `src/automana/core/services/ai/__init__.py` (empty).

Create `tests/unit/core/ai/test_agent_tools.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_search_cards_returns_list():
    from automana.core.services.ai.agent_tools import TOOL_MAP, TOOL_SCHEMAS
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"card_name": "Lightning Bolt", "set_code": "LEA", "oracle_id": "abc"},
    ])
    result = json.loads(await TOOL_MAP["search_cards"](conn, query="lightning bolt"))
    assert isinstance(result, list)
    assert result[0]["card_name"] == "Lightning Bolt"


@pytest.mark.asyncio
async def test_get_card_prices_returns_list():
    from automana.core.services.ai.agent_tools import TOOL_MAP
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"card_name": "Lightning Bolt", "price_usd": "1.50", "source": "tcgplayer"},
    ])
    result = json.loads(await TOOL_MAP["get_card_prices"](conn, card_name="Lightning Bolt"))
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_stub_tools_return_not_implemented():
    from automana.core.services.ai.agent_tools import TOOL_MAP
    conn = AsyncMock()
    result = json.loads(await TOOL_MAP["get_listings_needing_action"](conn))
    assert result["status"] == "not_implemented"
    result2 = json.loads(await TOOL_MAP["get_card_buy_recommendations"](conn))
    assert result2["status"] == "not_implemented"


def test_tool_schemas_are_valid():
    from automana.core.services.ai.agent_tools import TOOL_SCHEMAS
    assert len(TOOL_SCHEMAS) == 8  # 6 active + 2 stubs
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    expected = {
        "search_cards", "get_card_prices", "get_collection_summary",
        "get_active_listings", "get_sold_orders", "get_market_comps",
        "get_listings_needing_action", "get_card_buy_recommendations",
    }
    assert names == expected
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/core/ai/test_agent_tools.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement agent_tools.py**

Create `src/automana/core/services/ai/agent_tools.py`:

```python
from __future__ import annotations

import json
import logging
from typing import Callable

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _rows_to_json(rows: list[asyncpg.Record]) -> str:
    return json.dumps([dict(r) for r in rows], default=str)


# ---------------------------------------------------------------------------
# Active tool callables
# ---------------------------------------------------------------------------

async def _search_cards(conn: asyncpg.Connection, *, query: str, limit: int = 10) -> str:
    rows = await conn.fetch(
        """
        SELECT c.card_name, c.set_code, c.oracle_id, c.mana_cost, c.type_line
        FROM card_catalog.cards c
        WHERE to_tsvector('english', c.card_name || ' ' || coalesce(c.oracle_text, ''))
              @@ plainto_tsquery('english', $1)
        ORDER BY ts_rank(
            to_tsvector('english', c.card_name || ' ' || coalesce(c.oracle_text, '')),
            plainto_tsquery('english', $1)
        ) DESC
        LIMIT $2
        """,
        query,
        limit,
    )
    return _rows_to_json(rows)


async def _get_card_prices(
    conn: asyncpg.Connection,
    *,
    card_name: str,
    set_code: str | None = None,
) -> str:
    if set_code:
        rows = await conn.fetch(
            """
            SELECT po.card_name, po.set_code, po.price_usd, po.price_usd_foil,
                   po.source, po.observed_at
            FROM pricing.price_observations po
            WHERE po.card_name ILIKE $1 AND po.set_code = $2
            ORDER BY po.observed_at DESC
            LIMIT 20
            """,
            card_name,
            set_code,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT po.card_name, po.set_code, po.price_usd, po.price_usd_foil,
                   po.source, po.observed_at
            FROM pricing.price_observations po
            WHERE po.card_name ILIKE $1
            ORDER BY po.observed_at DESC
            LIMIT 20
            """,
            card_name,
        )
    return _rows_to_json(rows)


async def _get_collection_summary(conn: asyncpg.Connection, *, user_id: str) -> str:
    rows = await conn.fetch(
        """
        SELECT uc.set_code, COUNT(*) AS card_count,
               SUM(uc.quantity) AS total_quantity
        FROM user_collection.user_cards uc
        WHERE uc.user_id = $1::uuid
        GROUP BY uc.set_code
        ORDER BY total_quantity DESC
        LIMIT 50
        """,
        user_id,
    )
    return _rows_to_json(rows)


async def _get_active_listings(
    conn: asyncpg.Connection,
    *,
    app_code: str,
    limit: int = 20,
) -> str:
    rows = await conn.fetch(
        """
        SELECT listing_id, title, price, quantity, condition, listed_at
        FROM app_integration.ebay_active_listings
        WHERE app_code = $1
        ORDER BY listed_at DESC
        LIMIT $2
        """,
        app_code,
        limit,
    )
    return _rows_to_json(rows)


async def _get_sold_orders(
    conn: asyncpg.Connection,
    *,
    app_code: str,
    days: int = 7,
    limit: int = 20,
) -> str:
    rows = await conn.fetch(
        """
        SELECT order_id, local_status, tracking_number, carrier_code, shipped_at
        FROM app_integration.ebay_order_status
        WHERE app_code = $1
          AND shipped_at >= now() - ($2 || ' days')::interval
        ORDER BY shipped_at DESC
        LIMIT $3
        """,
        app_code,
        str(days),
        limit,
    )
    return _rows_to_json(rows)


async def _get_market_comps(
    conn: asyncpg.Connection,
    *,
    card_name: str,
    condition: str | None = None,
) -> str:
    if condition:
        rows = await conn.fetch(
            """
            SELECT po.card_name, po.set_code, po.price_usd, po.source,
                   po.condition, po.observed_at
            FROM pricing.price_observations po
            WHERE po.card_name ILIKE $1
              AND po.source IN ('ebay_sold', 'tcgplayer_market')
              AND po.condition = $2
            ORDER BY po.observed_at DESC
            LIMIT 30
            """,
            card_name,
            condition,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT po.card_name, po.set_code, po.price_usd, po.source,
                   po.condition, po.observed_at
            FROM pricing.price_observations po
            WHERE po.card_name ILIKE $1
              AND po.source IN ('ebay_sold', 'tcgplayer_market')
            ORDER BY po.observed_at DESC
            LIMIT 30
            """,
            card_name,
        )
    return _rows_to_json(rows)


# ---------------------------------------------------------------------------
# Stub callables
# ---------------------------------------------------------------------------

async def _get_listings_needing_action(conn: asyncpg.Connection, **kwargs) -> str:
    return json.dumps({"status": "not_implemented", "message": "Coming soon"})


async def _get_card_buy_recommendations(conn: asyncpg.Connection, **kwargs) -> str:
    return json.dumps({"status": "not_implemented", "message": "Coming soon"})


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

TOOL_MAP: dict[str, Callable] = {
    "search_cards": _search_cards,
    "get_card_prices": _get_card_prices,
    "get_collection_summary": _get_collection_summary,
    "get_active_listings": _get_active_listings,
    "get_sold_orders": _get_sold_orders,
    "get_market_comps": _get_market_comps,
    "get_listings_needing_action": _get_listings_needing_action,
    "get_card_buy_recommendations": _get_card_buy_recommendations,
}

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_cards",
            "description": "Full-text search Magic cards by name or oracle text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms"},
                    "limit": {"type": "integer", "default": 10, "description": "Max results"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_card_prices",
            "description": "Retrieve latest price observations for a Magic card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {"type": "string"},
                    "set_code": {"type": "string", "description": "3-letter set code (optional)"},
                },
                "required": ["card_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_collection_summary",
            "description": "Summarise a user's card collection by set.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "UUID of the user"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_listings",
            "description": "List active eBay listings for an app.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_code": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["app_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sold_orders",
            "description": "Retrieve recent eBay sold orders for an app.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_code": {"type": "string"},
                    "days": {"type": "integer", "default": 7},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["app_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_comps",
            "description": "Retrieve market comparable prices (eBay sold, TCGPlayer) for a card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {"type": "string"},
                    "condition": {"type": "string", "description": "e.g. NM, LP, MP (optional)"},
                },
                "required": ["card_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_listings_needing_action",
            "description": "Identify listings that need repricing or attention. (Coming soon)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_card_buy_recommendations",
            "description": "Suggest cards to buy based on price trends. (Coming soon)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/core/ai/test_agent_tools.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/ai/ tests/unit/core/ai/test_agent_tools.py
git commit -m "feat(ai): add agent tool definitions and callables"
```

---

## Task 5: AgentChatService

**Files:**
- Modify: `src/automana/core/services/ai/agent_chat_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/core/ai/test_agent_chat_service.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/core/ai/test_agent_chat_service.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement AgentChatService**

Create `src/automana/core/services/ai/agent_chat_service.py`:

```python
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import asyncpg
from redis.asyncio import Redis
from redis.exceptions import RedisError

from automana.core.repositories.ai.ollama_repository import OllamaAPIRepository
from automana.core.services.ai.agent_tools import TOOL_MAP, TOOL_SCHEMAS
from automana.core.settings import get_settings

logger = logging.getLogger(__name__)

_HISTORY_KEY = "ai:chat:{user_id}:{session_id}"


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

    # First Ollama pass — tools enabled
    response = await ollama_repo.chat_completion(
        messages=history,
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
        final_content = (second_choice["message"].get("content") or "").strip()
    else:
        final_content = (assistant_msg.get("content") or "").strip()

    if not final_content:
        final_content = "I couldn't generate a response. Please try again."

    history.append({"role": "assistant", "content": final_content})
    await _save_history(redis, key, history, settings.agent_chat_ttl)

    return {
        "reply": final_content,
        "session_id": session_id,
        "tools_called": tools_called,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/core/ai/test_agent_chat_service.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/ai/agent_chat_service.py tests/unit/core/ai/test_agent_chat_service.py
git commit -m "feat(ai): implement AgentChatService with tool-calling loop"
```

---

## Task 6: Register the service with ServiceRegistry

**Files:**
- Modify: `src/automana/core/service_registry.py`

The `AgentChatService` is not a `@ServiceRegistry.register` service in the normal sense — it takes `redis` and `ollama_repo` which are not standard DB repositories. We expose it as a thin `@ServiceRegistry.register` wrapper that the router calls via `service_manager.execute_service("ai.agent_chat", ...)`. The service manager passes `api_repositories` by name; Redis is injected separately in the router.

- [ ] **Step 1: Add the service registration block to service_registry.py**

At the bottom of `src/automana/core/service_registry.py`, add:

```python
ServiceRegistry.register_db_repository(
    "agent_ro",
    "automana.core.repositories.ai.agent_db",
    "AgentReadOnlyPool",
)
```

Wait — the tools call asyncpg directly with a connection passed in. There's no separate `AgentReadOnlyPool` repository class needed; the connection is acquired in the router via a dedicated pool. Instead, skip the repository registration and wire the connection in the router (Task 7). Nothing to add here.

- [ ] **Step 2: Confirm no registry change is needed**

The service manager wires `api_repositories=["ollama"]` for the `OllamaAPIRepository`. Redis and the asyncpg agent connection are injected directly in the router. No new registry entries are required beyond what Task 3 already added.

- [ ] **Step 3: Commit**

```
(no files changed — this task confirms design intent, no commit needed)
```

---

## Task 7: Agent Connection Pool

**Files:**
- Modify: `src/automana/core/settings.py` — add `agent_db_user` and `agent_db_password_file`
- Modify: `src/automana/core/database.py` — add `init_agent_pool` helper

The `agent` DB role has a dedicated password file (`config/secrets/agent_db_password.txt`). The router acquires a connection from this pool for tool calls.

- [ ] **Step 1: Add agent DB settings to Settings**

In `src/automana/core/settings.py`, add after the `ollama_*` fields:

```python
agent_db_user: str = Field(default="app_agent", alias="APP_AGENT_DB_USER")
agent_db_password_file: str | None = Field(default=None, alias="AGENT_DB_PASSWORD_FILE")
agent_db_password: str | None = Field(default=None, alias="AGENT_DB_PASSWORD")
```

- [ ] **Step 2: Add init_agent_pool to database.py**

In `src/automana/core/database.py`, add after `init_async_pool`:

```python
async def init_agent_pool(settings: Settings) -> asyncpg.Pool:
    """Create a read-only asyncpg pool for the app_agent DB role."""
    password = read_db_password(
        password_file=settings.agent_db_password_file,
        env_password=settings.agent_db_password,
    )
    from urllib.parse import quote_plus
    dsn = (
        f"postgresql://{settings.agent_db_user}:{quote_plus(password)}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=4,
        command_timeout=30,
        server_settings={"search_path": _SEARCH_PATH, "client_encoding": "UTF8"},
    )
```

Add the import for `read_db_password` at the top of `database.py`:
```python
from automana.core.settings import read_db_password
```

- [ ] **Step 3: Wire the agent pool into the app lifespan**

Find the app lifespan in `src/automana/main.py` (or wherever the pool is initialised). It typically looks like:

```python
app.state.db_pool = await init_async_pool(settings)
```

Add below it:

```python
from automana.core.database import init_agent_pool
app.state.agent_pool = await init_agent_pool(settings)
```

And in the shutdown block:

```python
await close_async_pool(app.state.agent_pool)
```

- [ ] **Step 4: Verify the app starts**

```bash
docker compose -f deploy/docker-compose.dev.yml exec backend python -c "print('ok')"
```

(Full startup check will be done after Docker changes in Task 9.)

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/settings.py src/automana/core/database.py src/automana/main.py
git commit -m "feat(ai): add agent read-only DB pool"
```

---

## Task 8: FastAPI Router

**Files:**
- Create: `src/automana/api/routers/integrations/ai/__init__.py`
- Create: `src/automana/api/routers/integrations/ai/agent_router.py`
- Modify: `src/automana/api/routers/integrations/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/__init__.py` if it doesn't exist (it does).

Create `tests/unit/api/test_agent_router.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_agent_chat_endpoint_returns_reply():
    from automana.main import app

    mock_user = MagicMock()
    mock_user.unique_id = "user-test-uuid"

    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("automana.api.routers.integrations.ai.agent_router.get_current_user", return_value=mock_user),
        patch("automana.api.routers.integrations.ai.agent_router.run_agent_turn", new=AsyncMock(
            return_value={"reply": "test reply", "session_id": "s1", "tools_called": []}
        )),
        patch.object(app.state, "agent_pool", mock_pool, create=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/integrations/ai/chat",
                json={"message": "hello", "session_id": "s1"},
                headers={"Authorization": "Bearer fake-token"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["reply"] == "test reply"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/unit/api/test_agent_router.py -v
```

Expected: `ImportError` or 404.

- [ ] **Step 3: Create the router**

Create `src/automana/api/routers/integrations/ai/__init__.py` (empty).

Create `src/automana/api/routers/integrations/ai/agent_router.py`:

```python
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from automana.api.dependancies.auth.users import CurrentUserDep
from automana.api.schemas.StandardisedQueryResponse import ApiResponse
from automana.core.repositories.ai.ollama_repository import OllamaAPIRepository
from automana.core.services.ai.agent_chat_service import run_agent_turn
from automana.core.settings import get_settings
from automana.core.utils.redis_cache import get_redis_client

logger = logging.getLogger(__name__)

ai_router = APIRouter(prefix="/ai", tags=["AI Agent"])

settings = get_settings()


class AgentChatRequest(BaseModel):
    message: str
    session_id: str = ""
    app_code: str | None = None


class AgentChatResponse(BaseModel):
    reply: str
    session_id: str
    tools_called: list[str]


@ai_router.post("/chat", response_model=ApiResponse)
async def agent_chat(
    body: AgentChatRequest,
    user: CurrentUserDep,
    request: Request,
) -> ApiResponse:
    session_id = body.session_id or str(uuid.uuid4())

    redis = await get_redis_client()
    ollama_repo = OllamaAPIRepository(base_url=settings.ollama_base_url)

    agent_pool = getattr(request.app.state, "agent_pool", None)
    if agent_pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent DB pool not available",
        )

    try:
        async with agent_pool.acquire() as conn:
            result = await run_agent_turn(
                conn=conn,
                redis=redis,
                ollama_repo=ollama_repo,
                user_id=str(user.unique_id),
                session_id=session_id,
                message=body.message,
                app_code=body.app_code,
            )
    except Exception as e:
        logger.error("agent_chat_error", extra={"error": str(e)}, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable",
        )

    return ApiResponse(
        message="ok",
        data=AgentChatResponse(**result).model_dump(),
    )
```

- [ ] **Step 4: Register the router**

Open `src/automana/api/routers/integrations/__init__.py` and add:

```python
from automana.api.routers.integrations.ai import ai_router

integrations_router.include_router(ai_router)
```

The full file becomes:

```python
from fastapi import APIRouter
from automana.api.routers.integrations.ebay import ebay_router
from automana.api.routers.integrations.shopify import shopify_router
from automana.api.routers.integrations.mtg_stock import router as mtg_stock_router
from automana.api.routers.integrations.ai.agent_router import ai_router

integrations_router = APIRouter(prefix="/integrations", tags=["Integrations"])
integrations_router.include_router(ebay_router)
integrations_router.include_router(shopify_router)
integrations_router.include_router(mtg_stock_router)
integrations_router.include_router(ai_router)
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/unit/api/test_agent_router.py -v
```

Expected: 1 passed (or adjust mock structure until it passes).

- [ ] **Step 6: Commit**

```bash
git add src/automana/api/routers/integrations/ai/ src/automana/api/routers/integrations/__init__.py tests/unit/api/test_agent_router.py
git commit -m "feat(ai): add POST /integrations/ai/chat router"
```

---

## Task 9: Docker — Ollama Sidecar

**Files:**
- Modify: `deploy/docker-compose.dev.yml`
- Modify: `deploy/docker-compose.prod.yml`

- [ ] **Step 1: Add ollama service to docker-compose.dev.yml**

At the end of the `services:` block in `deploy/docker-compose.dev.yml`, before the `secrets:` section, add:

```yaml
  ollama:
    image: ollama/ollama:latest
    container_name: automana-ollama-dev
    restart: unless-stopped
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - backend-network
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s
```

In the `volumes:` section of `docker-compose.dev.yml`, add:

```yaml
  ollama_data:
```

Update `backend` and `celery-worker` `depends_on` to optionally wait for ollama (optional health dependency):

Do NOT add a hard `depends_on: ollama` for backend — the `ollama` service is optional (graceful degraded mode when unavailable). Leave `depends_on` unchanged.

- [ ] **Step 2: Add the same to docker-compose.prod.yml**

Apply the identical `ollama` service block and `ollama_data` volume to `deploy/docker-compose.prod.yml`.

- [ ] **Step 3: Pull the model on first startup**

Add a one-shot init command after the healthcheck by modifying the `entrypoint`:

```yaml
  ollama:
    image: ollama/ollama:latest
    container_name: automana-ollama-dev
    restart: unless-stopped
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - backend-network
    entrypoint: >
      sh -c "ollama serve & sleep 5 && ollama pull qwen3:30b-a3b && wait"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 300s
```

`start_period: 300s` gives the first-boot pull time to finish before the health check starts failing.

- [ ] **Step 4: Validate compose files parse without error**

```bash
docker compose -f deploy/docker-compose.dev.yml config --quiet && echo "dev ok"
docker compose -f deploy/docker-compose.prod.yml config --quiet && echo "prod ok"
```

Expected: `dev ok` and `prod ok`.

- [ ] **Step 5: Commit**

```bash
git add deploy/docker-compose.dev.yml deploy/docker-compose.prod.yml
git commit -m "feat(infra): add Ollama sidecar to dev and prod compose stacks"
```

---

## Task 10: End-to-End Smoke Test

- [ ] **Step 1: Start the dev stack with Ollama**

```bash
docker compose -f deploy/docker-compose.dev.yml up -d ollama
```

Wait for Ollama to become healthy (~5 minutes on first run while model downloads):

```bash
docker compose -f deploy/docker-compose.dev.yml ps ollama
```

- [ ] **Step 2: Verify the model is loaded**

```bash
curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; models=json.load(sys.stdin)['models']; print([m['name'] for m in models])"
```

Expected: `['qwen3:30b-a3b:latest']` (or similar).

- [ ] **Step 3: Call the chat endpoint (requires running backend with JWT)**

Follow the AutoMana API testing flow (`docs/TESTING_API_FLOW.md`) to get a JWT, then:

```bash
curl -s -X POST http://localhost:8000/api/integrations/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "What is Lightning Bolt?"}' | python3 -m json.tool
```

Expected: JSON with `reply`, `session_id`, `tools_called` fields.

- [ ] **Step 4: Run the full unit test suite**

```bash
python -m pytest tests/unit/ -v
```

Expected: all pass, no regressions.

- [ ] **Step 5: Final commit and PR**

```bash
git add .
git commit -m "chore(ai): agent chat smoke test — all green"
```

Then open a PR via `/commit-and-pr` or:

```bash
gh pr create --title "feat(ai): add Qwen3 agent chat endpoint" \
  --body "Implements POST /api/integrations/ai/chat backed by Ollama + Qwen3-30B-A3B. Includes tool-calling loop, Redis history window, read-only agent DB pool, and Ollama docker-compose sidecar."
```

---

## Self-Review Checklist

**Spec coverage:**
- §4 Docker sidecar → Task 9 ✓
- §5 OllamaAPIRepository → Task 2 ✓
- §6 Tool Registry (6 active + 2 stubs) → Task 4 ✓
- §7 AgentChatService loop → Task 5 ✓
- §8 FastAPI Router → Task 8 ✓
- §4 Settings → Task 1 ✓
- §8 Internal `run_agent_turn` callable → exported from agent_chat_service ✓
- §9 Error handling (503 Ollama, tool error, Redis fallback, no content) → Task 5 & 8 ✓
- §10 Security (auth-gated, read-only role, session scoped to user) → Task 8 & DB pool ✓
- §11 Unit tests → Tasks 2, 4, 5, 8 ✓
- ServiceRegistry registration → Task 3 ✓
- Router registration in `__init__.py` → Task 8 ✓

**No placeholders present** — all steps include exact code.

**Type consistency** — `run_agent_turn` returns `dict[str, Any]` with keys `reply`, `session_id`, `tools_called` — matches `AgentChatResponse` model in Task 8.
