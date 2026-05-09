import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LifecycleBadge } from '../LifecycleBadge'

describe('LifecycleBadge', () => {
  it('renders Sold for sold status', () => {
    render(<LifecycleBadge status="sold" />)
    expect(screen.getByText(/Sold/i)).toBeTruthy()
  })

  it('renders Sent for sent status', () => {
    render(<LifecycleBadge status="sent" />)
    expect(screen.getByText(/Sent/i)).toBeTruthy()
  })

  it('renders Transit for in_transit status', () => {
    render(<LifecycleBadge status="in_transit" />)
    expect(screen.getByText(/Transit/i)).toBeTruthy()
  })

  it('renders Done for complete status', () => {
    render(<LifecycleBadge status="complete" />)
    expect(screen.getByText(/Done/i)).toBeTruthy()
  })
})
