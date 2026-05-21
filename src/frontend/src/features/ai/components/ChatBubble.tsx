// src/frontend/src/features/ai/components/ChatBubble.tsx
import { useState } from 'react'
import { useAuthStore } from '../../../store/auth'
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
