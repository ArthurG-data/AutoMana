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
