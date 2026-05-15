// src/frontend/src/features/ai/components/__tests__/ResultStrip.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ResultStrip } from '../ResultStrip'

describe('ResultStrip', () => {
  it('renders nothing when toolsCalled is empty', () => {
    const { container } = render(<ResultStrip toolsCalled={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders card search indicator for search_cards', () => {
    render(<ResultStrip toolsCalled={['search_cards']} />)
    expect(screen.getByText('Card search')).toBeTruthy()
  })

  it('renders price lookup indicator for get_card_prices', () => {
    render(<ResultStrip toolsCalled={['get_card_prices']} />)
    expect(screen.getByText('Price lookup')).toBeTruthy()
  })

  it('renders price lookup indicator for get_market_comps', () => {
    render(<ResultStrip toolsCalled={['get_market_comps']} />)
    expect(screen.getByText('Price lookup')).toBeTruthy()
  })

  it('renders nothing for unrecognised tools', () => {
    const { container } = render(<ResultStrip toolsCalled={['get_active_listings']} />)
    expect(container.firstChild).toBeNull()
  })
})
