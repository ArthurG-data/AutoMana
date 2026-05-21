// src/frontend/src/features/ai/components/ChatWindow.tsx
import { useState, useRef, useEffect, Fragment } from 'react'
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

  async function send() {
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
  }

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
          <Fragment key={msg.id}>
            <ChatMessage message={msg} />
            {msg.role === 'assistant' && msg.toolsCalled.length > 0 && (
              <ResultStrip toolsCalled={msg.toolsCalled} />
            )}
          </Fragment>
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
