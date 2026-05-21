# AI Chat Bubble Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a floating AI chat bubble to every page of the AutoMana frontend, with two explicit modes (Find Cards / Check Prices) backed by the existing `POST /api/ai/chat` endpoint.

**Architecture:** New `features/ai/` folder with types, API wrapper, and five components. State lives entirely in `ChatWindow` local state (no Zustand store). `ChatBubble` is mounted once in `__root.tsx` and only renders when the user is authenticated.

**Tech Stack:** React 18, TypeScript, CSS Modules (existing `--hd-*` design tokens), Vitest + React Testing Library, MSW for API mocking.

---

## File Map

**Create:**
- `src/frontend/src/features/ai/types.ts` — shared types
- `src/frontend/src/features/ai/api.ts` — `postChatMessage` fetch wrapper
- `src/frontend/src/features/ai/components/ModeToggle.tsx` + `.module.css`
- `src/frontend/src/features/ai/components/ChatMessage.tsx` + `.module.css`
- `src/frontend/src/features/ai/components/ResultStrip.tsx` + `.module.css`
- `src/frontend/src/features/ai/components/ChatWindow.tsx` + `.module.css`
- `src/frontend/src/features/ai/components/ChatBubble.tsx` + `.module.css`
- `src/frontend/src/features/ai/components/__tests__/ModeToggle.test.tsx`
- `src/frontend/src/features/ai/components/__tests__/ChatMessage.test.tsx`
- `src/frontend/src/features/ai/components/__tests__/ResultStrip.test.tsx`
- `src/frontend/src/features/ai/components/__tests__/ChatWindow.test.tsx`
- `src/frontend/src/features/ai/components/__tests__/ChatBubble.test.tsx`
- `src/frontend/src/features/ai/__tests__/api.test.ts`

**Modify:**
- `src/frontend/src/mocks/handlers.ts` — add `POST /api/ai/chat` MSW handler
- `src/frontend/src/routes/__root.tsx` — mount `<ChatBubble />`

---

## Task 1: Types

**Files:**
- Create: `src/frontend/src/features/ai/types.ts`

- [ ] **Step 1: Create types file**

```typescript
// src/frontend/src/features/ai/types.ts

export type ChatMode = 'cards' | 'prices'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolsCalled: string[]
  isError: boolean
}

export interface ChatApiResponse {
  reply: string
  session_id: string
  tools_called: string[]
}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/features/ai/types.ts
git commit -m "feat(ai): add chat bubble types"
```

---

## Task 2: API Layer + MSW Handler

**Files:**
- Create: `src/frontend/src/features/ai/api.ts`
- Create: `src/frontend/src/features/ai/__tests__/api.test.ts`
- Modify: `src/frontend/src/mocks/handlers.ts`

- [ ] **Step 1: Add MSW handler**

Open `src/frontend/src/mocks/handlers.ts` and add this import at the top and handler in the `handlers` array:

```typescript
// add to existing imports at top of handlers.ts
// (no new import needed — http and HttpResponse are already imported)

// add inside the handlers array:
http.post('/api/ai/chat', async ({ request }) => {
  const body = await request.json() as { message: string; session_id?: string }
  const sessionId = body.session_id && body.session_id !== '' ? body.session_id : 'mock-session-123'
  return HttpResponse.json({
    success: true,
    data: {
      reply: `Mock reply for: ${body.message}`,
      session_id: sessionId,
      tools_called: [],
    },
  })
}),
```

- [ ] **Step 2: Write the failing test**

```typescript
// src/frontend/src/features/ai/__tests__/api.test.ts
import { describe, it, expect } from 'vitest'
import { postChatMessage } from '../api'

describe('postChatMessage', () => {
  it('sends message and returns reply with new session', async () => {
    const result = await postChatMessage({ message: 'find lightning bolt', sessionId: null })
    expect(result.reply).toBe('Mock reply for: find lightning bolt')
    expect(result.session_id).toBe('mock-session-123')
    expect(result.tools_called).toEqual([])
  })

  it('sends an existing session_id and echoes it back', async () => {
    const result = await postChatMessage({ message: 'hello', sessionId: 'abc-session' })
    expect(result.session_id).toBe('abc-session')
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd src/frontend && npx vitest run src/features/ai/__tests__/api.test.ts
```

Expected: FAIL — "Cannot find module '../api'"

- [ ] **Step 4: Implement the API wrapper**

```typescript
// src/frontend/src/features/ai/api.ts
import { apiClient } from '../../lib/apiClient'
import type { ChatApiResponse } from './types'

export interface PostChatMessageParams {
  message: string
  sessionId: string | null
}

export async function postChatMessage({ message, sessionId }: PostChatMessageParams): Promise<ChatApiResponse> {
  return apiClient<ChatApiResponse>('/ai/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      session_id: sessionId ?? '',
    }),
  })
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ai/__tests__/api.test.ts
```

Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ai/api.ts \
        src/frontend/src/features/ai/__tests__/api.test.ts \
        src/frontend/src/mocks/handlers.ts
git commit -m "feat(ai): add postChatMessage API wrapper and MSW handler"
```

---

## Task 3: ModeToggle Component

**Files:**
- Create: `src/frontend/src/features/ai/components/ModeToggle.tsx`
- Create: `src/frontend/src/features/ai/components/ModeToggle.module.css`
- Create: `src/frontend/src/features/ai/components/__tests__/ModeToggle.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// src/frontend/src/features/ai/components/__tests__/ModeToggle.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ModeToggle } from '../ModeToggle'

describe('ModeToggle', () => {
  it('renders Find Cards and Check Prices buttons', () => {
    render(<ModeToggle mode="cards" onModeChange={vi.fn()} />)
    expect(screen.getByText('Find Cards')).toBeTruthy()
    expect(screen.getByText('Check Prices')).toBeTruthy()
  })

  it('marks the active mode button as active via aria-pressed', () => {
    render(<ModeToggle mode="cards" onModeChange={vi.fn()} />)
    expect(screen.getByText('Find Cards').closest('button')?.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText('Check Prices').closest('button')?.getAttribute('aria-pressed')).toBe('false')
  })

  it('calls onModeChange with "prices" when Check Prices is clicked', () => {
    const onModeChange = vi.fn()
    render(<ModeToggle mode="cards" onModeChange={onModeChange} />)
    fireEvent.click(screen.getByText('Check Prices'))
    expect(onModeChange).toHaveBeenCalledWith('prices')
  })

  it('calls onModeChange with "cards" when Find Cards is clicked', () => {
    const onModeChange = vi.fn()
    render(<ModeToggle mode="prices" onModeChange={onModeChange} />)
    fireEvent.click(screen.getByText('Find Cards'))
    expect(onModeChange).toHaveBeenCalledWith('cards')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ModeToggle.test.tsx
```

Expected: FAIL — "Cannot find module '../ModeToggle'"

- [ ] **Step 3: Implement ModeToggle**

```typescript
// src/frontend/src/features/ai/components/ModeToggle.tsx
import type { ChatMode } from '../types'
import styles from './ModeToggle.module.css'

interface ModeToggleProps {
  mode: ChatMode
  onModeChange: (mode: ChatMode) => void
}

export function ModeToggle({ mode, onModeChange }: ModeToggleProps) {
  return (
    <div className={styles.toggle}>
      <button
        className={`${styles.btn} ${mode === 'cards' ? styles.active : ''}`}
        aria-pressed={mode === 'cards'}
        onClick={() => onModeChange('cards')}
      >
        Find Cards
      </button>
      <button
        className={`${styles.btn} ${mode === 'prices' ? styles.active : ''}`}
        aria-pressed={mode === 'prices'}
        onClick={() => onModeChange('prices')}
      >
        Check Prices
      </button>
    </div>
  )
}
```

```css
/* src/frontend/src/features/ai/components/ModeToggle.module.css */
.toggle {
  display: flex;
  gap: 4px;
  background: var(--hd-bg);
  border-radius: 8px;
  padding: 2px;
}

.btn {
  flex: 1;
  padding: 4px 10px;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  background: transparent;
  color: var(--hd-muted);
  transition: background 0.15s, color 0.15s;
}

.btn.active {
  background: var(--hd-surface);
  color: var(--hd-text);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ModeToggle.test.tsx
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ai/components/ModeToggle.tsx \
        src/frontend/src/features/ai/components/ModeToggle.module.css \
        src/frontend/src/features/ai/components/__tests__/ModeToggle.test.tsx
git commit -m "feat(ai): add ModeToggle component"
```

---

## Task 4: ChatMessage Component

**Files:**
- Create: `src/frontend/src/features/ai/components/ChatMessage.tsx`
- Create: `src/frontend/src/features/ai/components/ChatMessage.module.css`
- Create: `src/frontend/src/features/ai/components/__tests__/ChatMessage.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// src/frontend/src/features/ai/components/__tests__/ChatMessage.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ChatMessage } from '../ChatMessage'
import type { ChatMessage as ChatMessageType } from '../../types'

function makeMsg(overrides: Partial<ChatMessageType> = {}): ChatMessageType {
  return {
    id: '1',
    role: 'assistant',
    content: 'Hello there',
    toolsCalled: [],
    isError: false,
    ...overrides,
  }
}

describe('ChatMessage', () => {
  it('renders message content', () => {
    render(<ChatMessage message={makeMsg({ content: 'Find Lightning Bolt' })} />)
    expect(screen.getByText('Find Lightning Bolt')).toBeTruthy()
  })

  it('applies user class for user messages', () => {
    const { container } = render(<ChatMessage message={makeMsg({ role: 'user', content: 'hi' })} />)
    expect(container.querySelector('[data-role="user"]')).toBeTruthy()
  })

  it('applies assistant class for assistant messages', () => {
    const { container } = render(<ChatMessage message={makeMsg({ role: 'assistant', content: 'hi' })} />)
    expect(container.querySelector('[data-role="assistant"]')).toBeTruthy()
  })

  it('applies error styling for error messages', () => {
    const { container } = render(<ChatMessage message={makeMsg({ isError: true, content: 'Error!' })} />)
    expect(container.querySelector('[data-error="true"]')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ChatMessage.test.tsx
```

Expected: FAIL — "Cannot find module '../ChatMessage'"

- [ ] **Step 3: Implement ChatMessage**

```typescript
// src/frontend/src/features/ai/components/ChatMessage.tsx
import type { ChatMessage as ChatMessageType } from '../types'
import styles from './ChatMessage.module.css'

interface ChatMessageProps {
  message: ChatMessageType
}

export function ChatMessage({ message }: ChatMessageProps) {
  return (
    <div
      className={`${styles.message} ${message.role === 'user' ? styles.user : styles.assistant}`}
      data-role={message.role}
      data-error={message.isError || undefined}
    >
      <div className={`${styles.bubble} ${message.isError ? styles.error : ''}`}>
        {message.content}
      </div>
    </div>
  )
}
```

```css
/* src/frontend/src/features/ai/components/ChatMessage.module.css */
.message {
  display: flex;
  margin-bottom: 8px;
}

.user {
  justify-content: flex-end;
}

.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.user .bubble {
  background: var(--hd-accent, #3b82f6);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.assistant .bubble {
  background: var(--hd-surface);
  color: var(--hd-text);
  border: 1px solid var(--hd-border);
  border-bottom-left-radius: 4px;
}

.error {
  background: #fee2e2 !important;
  color: #dc2626 !important;
  border-color: #fca5a5 !important;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ChatMessage.test.tsx
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ai/components/ChatMessage.tsx \
        src/frontend/src/features/ai/components/ChatMessage.module.css \
        src/frontend/src/features/ai/components/__tests__/ChatMessage.test.tsx
git commit -m "feat(ai): add ChatMessage component"
```

---

## Task 5: ResultStrip Component

**Files:**
- Create: `src/frontend/src/features/ai/components/ResultStrip.tsx`
- Create: `src/frontend/src/features/ai/components/ResultStrip.module.css`
- Create: `src/frontend/src/features/ai/components/__tests__/ResultStrip.test.tsx`

**Note:** The `/api/ai/chat` response does not include raw tool results — only `tools_called` (the list of tool names that fired). `ResultStrip` renders a contextual indicator pill so the user knows which tool was invoked; the actual results live in the assistant's reply text.

- [ ] **Step 1: Write the failing test**

```typescript
// src/frontend/src/features/ai/components/__tests__/ResultStrip.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ResultStrip } from '../ResultStrip'

describe('ResultStrip', () => {
  it('renders nothing when toolsCalled is empty', () => {
    const { container } = render(<ResultStrip toolsCalled={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders card search indicator for search_cards', () => {
    render(<ResultStrip toolsCalled={['search_cards']} />)
    expect(screen.getByText('Card search')).toBeTruthy()
  })

  it('renders price lookup indicator for get_card_prices', () => {
    render(<ResultStrip toolsCalled={['get_card_prices']} />)
    expect(screen.getByText('Price lookup')).toBeTruthy()
  })

  it('renders price lookup indicator for get_market_comps', () => {
    render(<ResultStrip toolsCalled={['get_market_comps']} />)
    expect(screen.getByText('Price lookup')).toBeTruthy()
  })

  it('renders nothing for unrecognised tools', () => {
    const { container } = render(<ResultStrip toolsCalled={['get_active_listings']} />)
    expect(container.firstChild).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ResultStrip.test.tsx
```

Expected: FAIL — "Cannot find module '../ResultStrip'"

- [ ] **Step 3: Implement ResultStrip**

```typescript
// src/frontend/src/features/ai/components/ResultStrip.tsx
import styles from './ResultStrip.module.css'

interface ResultStripProps {
  toolsCalled: string[]
}

const CARD_TOOLS = new Set(['search_cards'])
const PRICE_TOOLS = new Set(['get_card_prices', 'get_market_comps'])

export function ResultStrip({ toolsCalled }: ResultStripProps) {
  const hasCardTool = toolsCalled.some((t) => CARD_TOOLS.has(t))
  const hasPriceTool = toolsCalled.some((t) => PRICE_TOOLS.has(t))

  if (!hasCardTool && !hasPriceTool) return null

  return (
    <div className={styles.strip}>
      {hasCardTool && (
        <span className={`${styles.pill} ${styles.cards}`}>
          Card search
        </span>
      )}
      {hasPriceTool && (
        <span className={`${styles.pill} ${styles.prices}`}>
          Price lookup
        </span>
      )}
    </div>
  )
}
```

```css
/* src/frontend/src/features/ai/components/ResultStrip.module.css */
.strip {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
  padding-left: 4px;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 500;
}

.cards {
  background: #dbeafe;
  color: #1d4ed8;
}

.prices {
  background: #dcfce7;
  color: #15803d;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ResultStrip.test.tsx
```

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ai/components/ResultStrip.tsx \
        src/frontend/src/features/ai/components/ResultStrip.module.css \
        src/frontend/src/features/ai/components/__tests__/ResultStrip.test.tsx
git commit -m "feat(ai): add ResultStrip component"
```

---

## Task 6: ChatWindow Component

**Files:**
- Create: `src/frontend/src/features/ai/components/ChatWindow.tsx`
- Create: `src/frontend/src/features/ai/components/ChatWindow.module.css`
- Create: `src/frontend/src/features/ai/components/__tests__/ChatWindow.test.tsx`

- [ ] **Step 1: Write the failing tests**

```typescript
// src/frontend/src/features/ai/components/__tests__/ChatWindow.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ChatWindow } from '../ChatWindow'

describe('ChatWindow', () => {
  it('renders mode toggle and input', () => {
    render(<ChatWindow onClose={vi.fn()} />)
    expect(screen.getByText('Find Cards')).toBeTruthy()
    expect(screen.getByText('Check Prices')).toBeTruthy()
    expect(screen.getByPlaceholderText(/describe a card/i)).toBeTruthy()
  })

  it('changes placeholder when mode switches to prices', () => {
    render(<ChatWindow onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Check Prices'))
    expect(screen.getByPlaceholderText(/card name or price/i)).toBeTruthy()
  })

  it('does not submit empty messages', () => {
    render(<ChatWindow onClose={vi.fn()} />)
    const btn = screen.getByRole('button', { name: /send/i })
    fireEvent.click(btn)
    expect(screen.queryByRole('listitem')).toBeNull()
  })

  it('submits a message on Enter and shows user bubble', async () => {
    render(<ChatWindow onClose={vi.fn()} />)
    const input = screen.getByPlaceholderText(/describe a card/i)
    fireEvent.change(input, { target: { value: 'find lightning bolt' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByText('find lightning bolt')).toBeTruthy()
  })

  it('shows assistant reply after send', async () => {
    render(<ChatWindow onClose={vi.fn()} />)
    const input = screen.getByPlaceholderText(/describe a card/i)
    fireEvent.change(input, { target: { value: 'find lightning bolt' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => {
      expect(screen.getByText('Mock reply for: find lightning bolt')).toBeTruthy()
    })
  })

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn()
    render(<ChatWindow onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ChatWindow.test.tsx
```

Expected: FAIL — "Cannot find module '../ChatWindow'"

- [ ] **Step 3: Implement ChatWindow**

```typescript
// src/frontend/src/features/ai/components/ChatWindow.tsx
import { useState, useRef, useEffect, useCallback } from 'react'
import { postChatMessage } from '../api'
import type { ChatMessage as ChatMessageType, ChatMode } from '../types'
import { ModeToggle } from './ModeToggle'
import { ChatMessage } from './ChatMessage'
import { ResultStrip } from './ResultStrip'
import styles from './ChatWindow.module.css'

interface ChatWindowProps {
  onClose: () => void
}

const PLACEHOLDER: Record<ChatMode, string> = {
  cards: 'Describe a card, color, effect…',
  prices: 'Card name or price query…',
}

export function ChatWindow({ onClose }: ChatWindowProps) {
  const [mode, setMode] = useState<ChatMode>('cards')
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const sessionIdRef = useRef<string | null>(null)
  const threadRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    }
  }, [messages, isLoading])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || isLoading) return

    const userMsg: ChatMessageType = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      toolsCalled: [],
      isError: false,
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    try {
      const result = await postChatMessage({ message: text, sessionId: sessionIdRef.current })
      sessionIdRef.current = result.session_id
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: result.reply,
          toolsCalled: result.tools_called,
          isError: false,
        },
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'The assistant is offline, try again later.',
          toolsCalled: [],
          isError: true,
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }, [input, isLoading])

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className={styles.window}>
      <div className={styles.header}>
        <ModeToggle mode={mode} onModeChange={setMode} />
        <button className={styles.closeBtn} onClick={onClose} aria-label="close">✕</button>
      </div>

      <div className={styles.thread} ref={threadRef}>
        {messages.map((msg) => (
          <div key={msg.id}>
            <ChatMessage message={msg} />
            {msg.role === 'assistant' && msg.toolsCalled.length > 0 && (
              <ResultStrip toolsCalled={msg.toolsCalled} />
            )}
          </div>
        ))}
        {isLoading && (
          <div className={styles.typing}>
            <span />
            <span />
            <span />
          </div>
        )}
      </div>

      <div className={styles.inputRow}>
        <input
          className={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={PLACEHOLDER[mode]}
          disabled={isLoading}
        />
        <button
          className={styles.sendBtn}
          onClick={send}
          disabled={isLoading || !input.trim()}
          aria-label="send"
        >
          ↑
        </button>
      </div>
    </div>
  )
}
```

```css
/* src/frontend/src/features/ai/components/ChatWindow.module.css */
.window {
  display: flex;
  flex-direction: column;
  width: 360px;
  height: 480px;
  background: var(--hd-bg, #fff);
  border: 1px solid var(--hd-border);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--hd-border);
  flex-shrink: 0;
}

.closeBtn {
  background: transparent;
  border: none;
  color: var(--hd-muted);
  cursor: pointer;
  font-size: 14px;
  padding: 4px;
  border-radius: 4px;
  line-height: 1;
}

.thread {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.typing {
  display: flex;
  gap: 4px;
  padding: 8px 4px;
  align-items: center;
}

.typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--hd-muted);
  animation: bounce 1.2s infinite;
}

.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-6px); }
}

.inputRow {
  display: flex;
  gap: 6px;
  padding: 10px 12px;
  border-top: 1px solid var(--hd-border);
  flex-shrink: 0;
}

.input {
  flex: 1;
  padding: 7px 10px;
  border: 1px solid var(--hd-border);
  border-radius: 8px;
  font-size: 13px;
  background: var(--hd-surface);
  color: var(--hd-text);
  outline: none;
}

.input:focus {
  border-color: var(--hd-accent, #3b82f6);
}

.sendBtn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: var(--hd-accent, #3b82f6);
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sendBtn:disabled {
  background: var(--hd-muted);
  cursor: not-allowed;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ChatWindow.test.tsx
```

Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ai/components/ChatWindow.tsx \
        src/frontend/src/features/ai/components/ChatWindow.module.css \
        src/frontend/src/features/ai/components/__tests__/ChatWindow.test.tsx
git commit -m "feat(ai): add ChatWindow component with multi-turn session support"
```

---

## Task 7: ChatBubble Component

**Files:**
- Create: `src/frontend/src/features/ai/components/ChatBubble.tsx`
- Create: `src/frontend/src/features/ai/components/ChatBubble.module.css`
- Create: `src/frontend/src/features/ai/components/__tests__/ChatBubble.test.tsx`

- [ ] **Step 1: Write the failing tests**

```typescript
// src/frontend/src/features/ai/components/__tests__/ChatBubble.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ChatBubble } from '../ChatBubble'

describe('ChatBubble', () => {
  it('renders the chat bubble button', () => {
    render(<ChatBubble />)
    expect(screen.getByRole('button', { name: /open chat/i })).toBeTruthy()
  })

  it('opens ChatWindow when bubble is clicked', () => {
    render(<ChatBubble />)
    fireEvent.click(screen.getByRole('button', { name: /open chat/i }))
    expect(screen.getByText('Find Cards')).toBeTruthy()
  })

  it('closes ChatWindow when close button inside it is clicked', () => {
    render(<ChatBubble />)
    fireEvent.click(screen.getByRole('button', { name: /open chat/i }))
    expect(screen.getByText('Find Cards')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(screen.queryByText('Find Cards')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ChatBubble.test.tsx
```

Expected: FAIL — "Cannot find module '../ChatBubble'"

- [ ] **Step 3: Implement ChatBubble**

```typescript
// src/frontend/src/features/ai/components/ChatBubble.tsx
import { useState } from 'react'
import { useAuthStore } from '../../../../store/auth'
import { ChatWindow } from './ChatWindow'
import styles from './ChatBubble.module.css'

export function ChatBubble() {
  const token = useAuthStore((s) => s.token)
  const [isOpen, setIsOpen] = useState(false)

  if (!token) return null

  return (
    <div className={styles.container}>
      {isOpen && <ChatWindow onClose={() => setIsOpen(false)} />}
      <button
        className={`${styles.bubble} ${isOpen ? styles.active : ''}`}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label="open chat"
        aria-expanded={isOpen}
      >
        💬
      </button>
    </div>
  )
}
```

```css
/* src/frontend/src/features/ai/components/ChatBubble.module.css */
.container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

.bubble {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: none;
  background: var(--hd-accent, #3b82f6);
  color: #fff;
  font-size: 22px;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s, box-shadow 0.15s;
}

.bubble:hover {
  transform: scale(1.06);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.22);
}

.bubble.active {
  background: var(--hd-text, #0f172a);
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd src/frontend && npx vitest run src/features/ai/components/__tests__/ChatBubble.test.tsx
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ai/components/ChatBubble.tsx \
        src/frontend/src/features/ai/components/ChatBubble.module.css \
        src/frontend/src/features/ai/components/__tests__/ChatBubble.test.tsx
git commit -m "feat(ai): add ChatBubble floating button component"
```

---

## Task 8: Wire Into Root + Smoke Test

**Files:**
- Modify: `src/frontend/src/routes/__root.tsx`

- [ ] **Step 1: Mount ChatBubble in `__root.tsx`**

Open `src/frontend/src/routes/__root.tsx` and apply these changes:

Add import after the existing imports:
```typescript
import { ChatBubble } from '../features/ai/components/ChatBubble'
```

Replace the `RootComponent` function body:
```typescript
function RootComponent() {
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const prevTokenRef = useRef(token)

  useEffect(() => {
    const wasAuthenticated = prevTokenRef.current !== null
    const isNowUnauthenticated = token === null
    if (wasAuthenticated && isNowUnauthenticated) {
      navigate({ to: '/search' })
    }
    prevTokenRef.current = token
  }, [token, navigate])

  return (
    <>
      <Outlet />
      <ChatBubble />
    </>
  )
}
```

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
cd src/frontend && npx vitest run
```

Expected: all pre-existing tests PASS, all new ai/ tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/routes/__root.tsx
git commit -m "feat(ai): mount ChatBubble in root layout"
```

---

## Task 9: Manual Smoke Test

- [ ] **Step 1: Start the dev server**

```bash
cd src/frontend && npm run dev
```

- [ ] **Step 2: Log in and verify the bubble appears**

Open `http://localhost:5173` (or the configured port), log in, and confirm:
- Chat bubble icon appears in the bottom-right corner.
- Clicking the bubble opens the ChatWindow.
- Mode toggle switches placeholder text between "Describe a card, color, effect…" and "Card name or price query…".
- Typing a message and pressing Enter shows the user bubble immediately.
- The typing indicator appears while waiting.
- A reply appears (requires Ollama running; if offline, the error bubble "The assistant is offline, try again later." should show).
- Clicking ✕ closes the window.
- Bubble is absent on the `/login` and `/search` public pages (unauthenticated).

- [ ] **Step 3: Final commit (if any tweaks were made)**

```bash
git add -p  # stage only intentional tweaks
git commit -m "fix(ai): smoke test adjustments"
```
