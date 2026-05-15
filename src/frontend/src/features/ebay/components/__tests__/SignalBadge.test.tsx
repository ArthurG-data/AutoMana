import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { SignalBadge } from '../SignalBadge'

describe('SignalBadge', () => {
  it('renders "↑ Raise" for action="raise"', () => {
    render(<SignalBadge action="raise" />)
    expect(screen.getByText(/Raise/)).toBeTruthy()
  })

  it('renders "↓ Lower" for action="lower"', () => {
    render(<SignalBadge action="lower" />)
    expect(screen.getByText(/Lower/)).toBeTruthy()
  })

  it('renders "— Hold" for action="hold"', () => {
    render(<SignalBadge action="hold" />)
    expect(screen.getByText(/Hold/)).toBeTruthy()
  })

  it('renders "✕ Draft" for action="draft"', () => {
    render(<SignalBadge action="draft" />)
    expect(screen.getByText(/Draft/)).toBeTruthy()
  })

  it('renders nothing for action=null', () => {
    const { container } = render(<SignalBadge action={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows confidence percentage when confidence prop is provided', () => {
    render(<SignalBadge action="raise" confidence={0.9} />)
    expect(screen.getByText(/90%/)).toBeTruthy()
  })
})
