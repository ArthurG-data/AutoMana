// src/frontend/src/features/ai/components/__tests__/ChatBubble.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { ChatBubble } from '../ChatBubble'
import { useAuthStore } from '../../../../store/auth'

beforeEach(() => {
  useAuthStore.setState({ token: 'test-token', currentUser: { username: 'test', email: null } })
})

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

  it('renders nothing when user is not authenticated', () => {
    useAuthStore.setState({ token: null, currentUser: null })
    const { container } = render(<ChatBubble />)
    expect(container.firstChild).toBeNull()
  })
})
