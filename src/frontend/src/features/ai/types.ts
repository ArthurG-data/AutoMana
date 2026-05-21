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
