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
