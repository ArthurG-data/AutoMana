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
