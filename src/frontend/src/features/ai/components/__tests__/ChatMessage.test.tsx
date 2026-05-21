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
