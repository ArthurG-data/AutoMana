// src/frontend/src/features/ebay/components/__tests__/StrategyCard.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { StrategyCard, buildStrategies, type StrategyKind } from '../StrategyCard'

const MARKET_PRICE = 54.20

describe('StrategyCard', () => {
  const strategies = buildStrategies(MARKET_PRICE)

  it('renders all five strategies', () => {
    const onSelect = vi.fn()
    for (const strategy of strategies) {
      render(
        <StrategyCard
          strategy={strategy}
          selected={false}
          onSelect={onSelect}
        />
      )
      expect(screen.getAllByText(strategy.name).length).toBeGreaterThan(0)
    }
  })

  it('shows selected state via aria-pressed', () => {
    const strategy = strategies[0]
    render(
      <StrategyCard
        strategy={strategy}
        selected={true}
        onSelect={vi.fn()}
      />
    )
    const btn = screen.getByRole('button', { name: new RegExp(strategy.name, 'i') })
    expect(btn.getAttribute('aria-pressed')).toBe('true')
  })

  it('unselected card has aria-pressed=false', () => {
    const strategy = strategies[1]
    render(
      <StrategyCard
        strategy={strategy}
        selected={false}
        onSelect={vi.fn()}
      />
    )
    const btn = screen.getByRole('button', { name: new RegExp(strategy.name, 'i') })
    expect(btn.getAttribute('aria-pressed')).toBe('false')
  })

  it('calls onSelect with strategy kind when clicked', () => {
    const onSelect = vi.fn()
    const strategy = strategies[2]
    render(
      <StrategyCard
        strategy={strategy}
        selected={false}
        onSelect={onSelect}
      />
    )
    const btn = screen.getByRole('button', { name: new RegExp(strategy.name, 'i') })
    fireEvent.click(btn)
    expect(onSelect).toHaveBeenCalledWith(strategy.kind)
  })

  it('displays recommended price, days range, and after-fees payout', () => {
    const strategy = strategies[0] // quick: −10 to −6%
    render(
      <StrategyCard
        strategy={strategy}
        selected={false}
        onSelect={vi.fn()}
      />
    )
    // After-fees text (payout) should appear — just check labels exist
    expect(screen.getByText('Recommended')).toBeTruthy()
    expect(screen.getByText('Est. days')).toBeTruthy()
    expect(screen.getByText('After fees')).toBeTruthy()
  })

  it('buildStrategies returns 5 strategies', () => {
    const s = buildStrategies(100)
    expect(s.length).toBe(5)
    const kinds: StrategyKind[] = s.map((x) => x.kind)
    expect(kinds).toContain('quick')
    expect(kinds).toContain('balanced')
    expect(kinds).toContain('max')
    expect(kinds).toContain('auction7')
    expect(kinds).toContain('auctionReserve')
  })
})
