# AI Agent — Future Roadmap

Current state: the chat bubble works, tools hit the real DB, and the model returns clean prose. This document describes what needs to happen next, in rough priority order.

---

## 1. Structured Data Responses (highest impact)

**Problem:** The API currently returns only a text `reply`. The frontend renders it as a plain string, so search results look like a bulleted list of text — the model decides the formatting and often gets it wrong or verbose.

**Solution:** Extend the API response to include structured payloads alongside the prose.

### Backend changes

```python
# agent_router.py — extend AgentChatResponse
class AgentChatResponse(BaseModel):
    reply: str
    session_id: str
    tools_called: list[str]
    cards: list[dict] | None = None      # from search_cards
    prices: list[dict] | None = None     # from get_card_prices / get_market_comps
```

In `run_agent_turn`, after tool execution, parse the JSON tool results and attach them:

```python
# agent_chat_service.py
structured: dict[str, list] = {}
for fn_name, raw_result in tool_results:
    if fn_name == "search_cards":
        structured["cards"] = json.loads(raw_result)
    elif fn_name in ("get_card_prices", "get_market_comps"):
        structured["prices"] = json.loads(raw_result)
```

### Frontend changes

Extend `ChatApiResponse` and `ChatMessage` types:

```ts
// types.ts
export interface CardResult {
  card_name: string
  set_code: string
  mana_cost: string
  type_line: string
  rarity_name: string
}

export interface PriceResult {
  card_name: string
  set_code: string
  finish: string
  list_avg_cents: number | null
  provider: string
  ts_date: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolsCalled: string[]
  isError: boolean
  cards?: CardResult[]       // structured card results
  prices?: PriceResult[]     // structured price results
}
```

Render them as `CardResultList` / `PriceTable` components below the prose reply instead of relying on the model to format them as text.

---

## 2. Rich Result Components

### CardChip

A compact row showing the card name, set badge, mana cost, and type — with a link to the card detail page.

```
┌─────────────────────────────────────────────┐
│ 🃏 Sheoldred, the Apocalypse   DMU  {2}{B}{B}│
│    Legendary Creature — Phyrexian Praetor   │
│    Mythic                          → Details│
└─────────────────────────────────────────────┘
```

Clicking "Details" navigates to `/catalog/cards/:card_version_id`.

### PriceTable

A two-column table: finish (NONFOIL / FOIL / ETCHED) × latest price in USD (cents ÷ 100). Group by set when multiple printings are returned.

```
 Sheoldred, the Apocalypse
 ──────────────────────────────────────
 DMU  │ NONFOIL │ $12.40  │ scryfall
 DMU  │ FOIL    │ $28.00  │ scryfall
 ──────────────────────────────────────
 Last updated: 2026-05-11
```

### Markdown rendering

The model reply should render as Markdown, not plain text. Use a lightweight renderer (e.g., `marked` or `micromark` — both are small and already available in many setups). Bold card names, `code` for set codes, and headings if the model uses them.

---

## 3. New Tools

Each tool needs:
- A function in `agent_tools.py`
- A schema entry in `TOOL_SCHEMAS`
- A key in `TOOL_MAP`

### `get_price_history(card_name, days=30)`

Query `pricing.price_observation` ordered by `ts_date` for the last N days. Return a time-series list. Frontend renders a tiny sparkline.

```sql
SELECT po.ts_date, cf.code AS finish, po.list_avg_cents
FROM pricing.price_observation po
JOIN pricing.source_product sp USING (source_product_id)
JOIN pricing.mtg_card_products mcp USING (product_id)
JOIN card_catalog.card_version cv USING (card_version_id)
JOIN card_catalog.unique_cards_ref ucr USING (unique_card_id)
JOIN card_catalog.card_finished cf USING (finish_id)
WHERE ucr.card_name ILIKE $1
  AND po.ts_date >= CURRENT_DATE - $2
ORDER BY po.ts_date, cf.code
```

### `get_format_legality(card_name)`

```sql
SELECT f.format_name, l.legal_status
FROM card_catalog.legalities l
JOIN card_catalog.legal_status_ref lst USING (legal_status_id)
JOIN card_catalog.formats_ref f USING (format_id)
JOIN card_catalog.unique_cards_ref ucr USING (unique_card_id)
WHERE ucr.card_name ILIKE $1
ORDER BY f.format_name
```

### `estimate_collection_value(user_id)`

Join the user's collection items to the latest price observations and sum up list_avg_cents. Group by finish. Useful for "how much is my collection worth?"

```sql
SELECT
    cf.code AS finish,
    COUNT(*) AS card_count,
    SUM(po.list_avg_cents) / 100.0 AS total_usd
FROM user_collection.collections c
JOIN user_collection.collection_items ci USING (collection_id)
JOIN card_catalog.card_finished cf USING (finish_id)
LEFT JOIN LATERAL (
    SELECT po.list_avg_cents
    FROM pricing.price_observation po
    JOIN pricing.source_product sp USING (source_product_id)
    JOIN pricing.mtg_card_products mcp ON mcp.product_id = sp.product_id
        AND mcp.card_version_id = ci.unique_card_id
    WHERE po.ts_date = (SELECT MAX(ts_date) FROM pricing.price_observation)
    LIMIT 1
) po ON true
WHERE c.user_id = $1::uuid AND c.is_active = true
GROUP BY cf.code
```

### `get_set_info(set_code)`

```sql
SELECT set_name, set_code, set_type, released_at, card_count
FROM card_catalog.sets
WHERE set_code ILIKE $1
```

### `search_cards_by_color(colors, max_cmc, type_line_contains)`

An advanced search mode letting the model answer "find me black creatures under 3 mana" by combining `color_identity`, `cmc`, and `type_line` filters on `v_card_versions_complete`.

### `get_top_price_movers(days=7, limit=10)` *(requires price history)*

Compare the most recent price to the price N days ago across all tracked cards. Return the cards with the largest absolute or percentage change. Good for "what spiked this week?"

---

## 4. Mode Toggle → Intent Detection

**Current state:** The user selects "Find Cards" or "Check Prices" via a tab before typing. This is redundant — the model already infers intent from the message.

**Proposed change:** Remove the toggle. Add a `mode` field to the system prompt automatically set by the model's tool selection, and reflect it visually in the ResultStrip (already color-coded blue for cards, green for prices).

If you keep the toggle, use it to constrain which tools are included in `TOOL_SCHEMAS` sent to the model — reducing context and preventing wrong-tool calls.

---

## 5. Suggested Queries (Chip Prompts)

Show 3–4 prompt chips when the chat is empty (before any message is sent). They disappear after the first message is sent.

```
┌─────────────────────────────────────────────┐
│  Try asking:                                │
│  [Find black creatures under 3 mana]        │
│  [What's Sheoldred worth today?]            │
│  [How much is my collection worth?]         │
│  [Show me format legality for Ragavan]      │
└─────────────────────────────────────────────┘
```

These are just `<button>` elements that call `send()` with a preset string.

---

## 6. Streaming Responses

**Problem:** Qwen3 30B takes 10–30 seconds to respond. The typing indicator helps but the wait feels long.

**Solution:** Switch to SSE streaming via Ollama's `stream: true`. The backend yields tokens as a `text/event-stream`, the frontend appends characters as they arrive.

Backend: convert `agent_router.py` to return `StreamingResponse`. Tool execution still blocks (can't stream mid-tool), but the second-pass prose streams in real time.

Frontend: Use `fetch` with `ReadableStream` in `api.ts`, updating the last assistant message in place as chunks arrive.

This alone makes the UX feel dramatically more responsive.

---

## 7. Chat History Persistence

**Current:** History lives in Redis with a TTL, keyed to `session_id`. If the user closes the bubble, the `sessionIdRef` is lost. Re-opening starts a new session.

**Proposed:** Persist `sessionIdRef` to `localStorage` keyed by user ID. On mount, restore the session ID and pre-populate the messages from a `/api/integrations/ai/history/:session_id` endpoint. Add a "New conversation" button to clear and reset.

---

## 8. System Prompt Tuning

The model currently has no system prompt — it receives only the user message and tool schemas. Add a concise system prompt:

```python
SYSTEM_PROMPT = """
You are an MTG collection assistant for AutoMana. 
You help users find cards, check prices, and manage their collection.
Always use the available tools to look up real data — never guess prices or set codes.
Reply concisely. Use Markdown formatting. When listing cards, use bold for card names.
If a tool returns no results, say so directly instead of speculating.
"""
```

Inject this as the first message in history on every turn.

---

## Implementation Order

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | System prompt | 30 min | High — stops hallucination |
| 2 | Markdown rendering in frontend | 1 h | High — readability |
| 3 | `get_price_history` tool | 2 h | High — core use case |
| 4 | `get_format_legality` tool | 1 h | High — common question |
| 5 | Structured data response + CardChip | 4 h | High — rich results |
| 6 | Suggested query chips | 1 h | Medium — discoverability |
| 7 | `get_set_info` tool | 1 h | Medium |
| 8 | `estimate_collection_value` tool | 3 h | Medium |
| 9 | Mode toggle → intent detection | 2 h | Medium |
| 10 | Chat history persistence (localStorage) | 2 h | Medium |
| 11 | Streaming responses | 6 h | Medium — UX polish |
| 12 | `get_top_price_movers` tool | 4 h | Low (requires price history data) |
| 13 | `search_cards_by_color` tool | 2 h | Low |
