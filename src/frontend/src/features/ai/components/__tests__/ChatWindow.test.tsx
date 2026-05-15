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
