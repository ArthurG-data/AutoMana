// src/frontend/src/features/cards/components/__tests__/MarketCard.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MarketCard } from '../MarketCard'

const BASE_PROPS = {
  price: 84.5,
  selectedFinish: 'nonfoil',
  finishes: ['nonfoil', 'foil', 'etched'],
  onFinishChange: vi.fn(),
  delta1d: 2.4,
  delta7d: 6.1,
  delta30d: -3.2,
}

describe('MarketCard', () => {
  it('shows the market price label with selected finish', () => {
    render(<MarketCard {...BASE_PROPS} />)
    expect(screen.getByText(/MARKET PRICE · nonfoil/)).toBeTruthy()
  })

  it('renders the integer and cents portions of price', () => {
    const { container } = render(<MarketCard {...BASE_PROPS} price={42.5} />)
    expect(container.textContent).toContain('$42')
    expect(container.textContent).toContain('.50')
  })

  it('renders N/A when price is null', () => {
    render(<MarketCard {...BASE_PROPS} price={null} />)
    expect(screen.getByText('N/A')).toBeTruthy()
  })

  it('renders three deltas with absolute values', () => {
    const { container } = render(<MarketCard {...BASE_PROPS} />)
    expect(container.textContent).toContain('2.40%')
    expect(container.textContent).toContain('6.10%')
    expect(container.textContent).toContain('3.20%')
  })

  it('uses up class for positive deltas and down class for negative deltas', () => {
    const { container } = render(
      <MarketCard {...BASE_PROPS} delta1d={1} delta7d={-2} delta30d={3} />
    )
    const ups = container.querySelectorAll('[class*="up"]').length
    const downs = container.querySelectorAll('[class*="down"]').length
    expect(ups).toBeGreaterThan(0)
    expect(downs).toBeGreaterThan(0)
  })

  it('renders one button per finish', () => {
    render(<MarketCard {...BASE_PROPS} />)
    expect(screen.getByRole('button', { name: 'nonfoil' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'foil' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'etched' })).toBeTruthy()
  })

  it('marks selected finish with aria-pressed=true', () => {
    render(<MarketCard {...BASE_PROPS} selectedFinish="foil" />)
    expect(screen.getByRole('button', { name: 'foil' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'nonfoil' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('calls onFinishChange with the clicked finish', () => {
    const onFinishChange = vi.fn()
    render(<MarketCard {...BASE_PROPS} onFinishChange={onFinishChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'foil' }))
    expect(onFinishChange).toHaveBeenCalledWith('foil')
  })
})
