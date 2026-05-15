# AI Chat Bubble — Design Spec

**Date:** 2026-05-15
**Branch:** feat/strategy-integration

---

## Overview

Add a floating AI chat bubble to the AutoMana frontend, accessible from every page. The bubble opens a chat window with two explicit modes — **Find Cards** and **Check Prices** — backed by the existing `/api/ai/chat` endpoint (Ollama + tool dispatch, Redis history).

No backend changes are required. The endpoint already returns `reply`, `session_id`, and `tools_called`, which is everything the frontend needs.

---

## Architecture

### Backend (unchanged)

- Endpoint: `POST /api/ai/chat`
- Payload: `{ message: string, session_id: string | null, app_code?: string }`
- Response: `{ data: { reply: string, session_id: string, tools_called: string[] } }`
- Tools relevant to this feature: `search_cards`, `get_card_prices`, `get_market_comps`

### Frontend — new feature folder

```
src/frontend/src/features/ai/
  api.ts               — React Query mutation wrapping POST /api/ai/chat
  types.ts             — ChatMessage, ChatMode, ChatResponse types
  components/
    ChatBubble.tsx     — fixed bottom-right toggle button
    ChatWindow.tsx     — chat panel (header, thread, input)
    ModeToggle.tsx     — "Find Cards" / "Check Prices" tab strip
    ChatMessage.tsx    — single message bubble (user or assistant)
    ResultStrip.tsx    — inline structured result below assistant messages
```

**Mount point:** `ChatBubble` is rendered inside `__root.tsx` so it persists across all routes.

---

## Components

### ChatBubble
- Fixed position, bottom-right corner.
- Chat icon button; click toggles the `ChatWindow` open/closed.
- Shows an unread indicator dot when the window is closed and a new reply has arrived.

### ChatWindow
- ~380px wide panel anchored above the bubble.
- Header: `ModeToggle` on the left, close button on the right.
- Scrollable message thread (auto-scrolls to latest message).
- Typing indicator (animated dots) while a response is pending.
- Input row: text field + send button. Enter key submits.

### ModeToggle
- Two tabs: `Find Cards` | `Check Prices`.
- Switching mode changes the input placeholder text only — chat history is preserved.
- Mode is UX guidance only; tool routing is handled automatically by the LLM based on message content.

### ChatMessage
- User messages: right-aligned, distinct background.
- Assistant messages: left-aligned.
- Below each assistant message: `ResultStrip` (rendered only when `tools_called` is non-empty).

### ResultStrip
Conditionally rendered based on `tools_called` from the API response:

| `tools_called` contains | Rendered output |
|---|---|
| `search_cards` | Horizontal list of card name chips. Each chip links to `/cards/:id` using the existing card search route. |
| `get_card_prices` or `get_market_comps` | Compact 3-column table: Card \| Set \| Price (USD) |
| Any other tool / empty | Nothing rendered |

---

## Data Flow

1. User selects mode (default: `Find Cards`).
2. User types a message and submits.
3. Optimistic user bubble added to the thread immediately.
4. `POST /api/ai/chat` fires with `{ message, session_id }`.
   - `session_id` is `null` on the first turn; subsequent turns use the value returned from the first response.
5. Typing indicator shown while the request is pending.
6. On success: assistant bubble rendered with `reply` text + `ResultStrip` if applicable.
7. On error: friendly error bubble in thread ("The assistant is offline, try again later."). No retry loop.

### Session lifecycle
- `session_id` is stored in component state, initialized to `null`.
- Set from the first API response and reused for all subsequent turns.
- Closing and reopening the chat window starts a new session (state is reset).

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| HTTP 503 (AI unavailable) | Error bubble: "The assistant is offline, try again later." |
| Network failure | Same error bubble with the caught error message. |
| Empty `reply` from backend | Backend already guards this — shown as-is. |
| Tool execution failure | LLM returns a prose error in `reply` — no special frontend handling needed. |

---

## Testing

- **Vitest unit tests:**
  - `ChatMessage` — renders user and assistant variants correctly.
  - `ResultStrip` — card chips for `search_cards`, price table for `get_card_prices`/`get_market_comps`, nothing for unknown tools.
- **MSW handler:** `POST /api/ai/chat` mocked in the existing `src/frontend/src/mocks/` setup.
- **No E2E tests:** Ollama is not available in CI.

---

## Out of Scope

- System prompt / mode-specific prompt injection (the LLM routes tools correctly without it).
- Persisting chat history across page reloads (Redis TTL handles server-side expiry; client state resets on window close).
- Rich card panels with images in `ResultStrip` (plain chips and price table are sufficient for v1).
- A dedicated `/chat` route.
