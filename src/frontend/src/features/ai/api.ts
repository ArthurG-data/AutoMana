// src/frontend/src/features/ai/api.ts
import { apiClient } from '../../lib/apiClient'
import type { ChatApiResponse } from './types'

export interface PostChatMessageParams {
  message: string
  sessionId: string | null
}

export async function postChatMessage({ message, sessionId }: PostChatMessageParams): Promise<ChatApiResponse> {
  return apiClient<ChatApiResponse>('/integrations/ai/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      session_id: sessionId ?? '',
    }),
  })
}
