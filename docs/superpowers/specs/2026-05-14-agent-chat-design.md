# Agent Chat — Design Spec
**Date:** 2026-05-14
**Status:** Approved

---

## 1. Purpose

Add a data-aware AI chatbot to AutoMana backed by a locally-hosted Qwen3-30B-A3B model (Ollama). The agent can answer MTG finance and collection questions using live AutoMana data, exposed both as a FastAPI endpoint (frontend chat UI) and as an internal callable (Celery tasks, other services).

---

## 2. Architecture

```
Frontend / Internal caller
        │
        ▼
POST /api/integrations/ai/chat        (FastAPI router — thin, auth-gated)
        │
        ▼
AgentChatService                      (service layer)
  ├── Redis   → conversation window (last N msgs, key: ai:chat:{user_id}:{session_id})
  ├── ToolRegistry → tool schemas (JSON) + async callables (read-only asyncpg)
  └── OllamaAPIRepository → POST http://ollama:11434/v1/chat/completions
                                    │
                                    ▼
                            Ollama container  (docker-compose sidecar)
                            Model: qwen3:30b-a3b
```

**Layers follow the existing AutoMana pattern:**
- Router → ServiceManager → Service → Repository (no skipping layers)
- `OllamaAPIRepository` extends `BaseApiClient` — same as Scryfall, eBay
- Tools use the existing read-only `agent` DB role via direct asyncpg (no ORM, no service layer calls)

---

## 3. New Files

| File | Purpose |
|------|---------|
| `src/automana/core/repositories/ai/ollama_repository.py` | `OllamaAPIRepository(BaseApiClient)` |
| `src/automana/core/services/ai/agent_tools.py` | Tool definitions (schemas + callables) |
| `src/automana/core/services/ai/agent_chat_service.py` | Conversation logic, tool dispatch loop |
| `src/automana/api/routers/integrations/ai/agent_router.py` | `POST /integrations/ai/chat` |
| `deploy/docker-compose.dev.yml` | Add `ollama` sidecar service |
| `deploy/docker-compose.prod.yml` | Add `ollama` sidecar service |

Register in:
- `src/automana/core/service_registry.py` — `ollama` API repository
- `src/automana/api/__init__.py` — agent router under `integrations_router`

---

## 4. Docker / Ollama Sidecar

```yaml
# added to both docker-compose.dev.yml and docker-compose.prod.yml
ollama:
  image: ollama/ollama:latest
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
    retries: 5
    start_period: 120s   # model pull takes time on first boot
```

Model is pulled on first startup via an `entrypoint` override or a one-shot init container. The `ollama_data` volume persists the model across restarts.

**Settings added to `core/settings.py`:**
```python
ollama_base_url: str = "http://ollama:11434"
ollama_model: str = "qwen3:30b-a3b"
agent_chat_window: int = 10        # messages kept per session
agent_chat_ttl: int = 7200         # Redis TTL in seconds (2h)
```

---

## 5. OllamaAPIRepository

Extends `BaseApiClient`. Implements `_get_base_url()` → `settings.ollama_base_url`.

Key method:
```python
async def chat_completion(
    self,
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.3,
) -> dict:
    """POST /v1/chat/completions — returns raw response dict."""
```

No streaming in v1 (simpler, sufficient for tool-calling loop). Streaming can be added later.

---

## 6. Tool Registry

`agent_tools.py` exposes two objects consumed by the service:

```python
TOOL_SCHEMAS: list[dict]   # JSON schemas sent to Qwen with every request
TOOL_MAP: dict[str, Callable]  # name → async callable(conn, **kwargs)
```

### Active tools (v1)

| Name | Signature | DB query |
|------|-----------|----------|
| `search_cards` | `query: str, limit: int = 10` | `card_catalog.cards` full-text search |
| `get_card_prices` | `card_name: str, set_code: str \| None` | `pricing.price_observations` latest |
| `get_collection_summary` | `user_id: str` | `card_catalog.user_collections` aggregates |
| `get_active_listings` | `app_code: str, limit: int = 20` | `app_integration.ebay_active_listings` |
| `get_sold_orders` | `app_code: str, days: int = 7, limit: int = 20` | `app_integration.ebay_order_status` |
| `get_market_comps` | `card_name: str, condition: str \| None` | `pricing.price_observations` external sold |

### Stub tools (future)

| Name | Returns |
|------|---------|
| `get_listings_needing_action` | `{"status": "not_implemented", "message": "Coming soon"}` |
| `get_card_buy_recommendations` | `{"status": "not_implemented", "message": "Coming soon"}` |

All callables receive an asyncpg `connection` opened under the `agent` read-only role. No writes permitted.

---

## 7. AgentChatService

### Request model
```python
class AgentChatRequest(BaseModel):
    message: str
    session_id: str = ""   # auto-generated UUID if blank
    app_code: str | None = None   # needed for listing tools
```

### Response model
```python
class AgentChatResponse(BaseModel):
    reply: str
    session_id: str
    tools_called: list[str]   # names of tools invoked this turn
```

### Conversation loop
```
1. Load history from Redis  (last agent_chat_window messages)
2. Append {"role": "user", "content": message}
3. POST to Ollama with messages + TOOL_SCHEMAS
4. If response.tool_calls:
     a. For each tool call:
          - Look up callable in TOOL_MAP
          - Execute with read-only asyncpg connection
          - Append {"role": "tool", "content": result_json, "tool_call_id": id}
     b. POST to Ollama again (second pass, no tools in schema to prevent loops)
5. Append {"role": "assistant", "content": final_reply} to history
6. Save updated history to Redis (reset TTL)
7. Return AgentChatResponse
```

Maximum one tool-calling round per request (prevents infinite loops). If Qwen requests tools on the second pass, they are ignored and the partial response is returned.

---

## 8. FastAPI Router

```
POST /api/integrations/ai/chat
  Auth: CurrentUserDep (JWT or session cookie)
  Body: AgentChatRequest
  Response: AgentChatResponse (200)
```

Router delegates entirely to `service_manager.execute_service("ai.agent_chat", ...)`. No business logic in the router.

### Internal usage (other services)
```python
from automana.core.services.ai.agent_chat_service import run_agent_turn

reply = await run_agent_turn(
    conn=conn,            # read-only agent connection
    redis=redis,
    ollama_repo=repo,
    user_id=user_id,
    session_id=session_id,
    message=prompt,
    app_code=app_code,
)
```

`run_agent_turn` is a plain async function — no ServiceRegistry required for internal callers.

---

## 9. Error Handling

| Failure | Behaviour |
|---------|-----------|
| Ollama unreachable | `503 Service Unavailable` with message "AI service temporarily unavailable" |
| Tool raises exception | Log error, append `{"role": "tool", "content": "Error retrieving data"}`, continue loop |
| Redis unavailable | Fall back to empty history (stateless degraded mode), no error to user |
| Qwen returns no content | Return `"I couldn't generate a response. Please try again."` |
| Unknown tool name | Skip silently, log warning |

---

## 10. Security

- Router is auth-gated — no anonymous access
- All tool queries run under the `agent` read-only DB role — no writes possible even if a tool is buggy
- `session_id` is scoped to `user_id` in the Redis key — users cannot access each other's history
- Ollama container is on `backend-network` only — not reachable from outside the compose stack

---

## 11. Testing

- Unit: `agent_chat_service` with mocked `OllamaAPIRepository` and Redis — verify history window slicing, tool dispatch, second-pass behaviour
- Integration: real Ollama (test container or local) with `search_cards` tool against test DB — verify end-to-end round trip
- Tool callables: each tool tested independently against the `agent` DB role to confirm read-only access and correct SQL
