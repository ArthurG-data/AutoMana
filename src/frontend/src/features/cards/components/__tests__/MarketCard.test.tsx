import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MarketCard } from '../MarketCard'
import { cardPriceHistoryQueryOptions } from '../api'
import { useUIStore } from '../../../../store/ui'

const noop = () => {}
const CARD_ID = '11111111-1111-1111-1111-111111111111'

afterEach(() => {
  // Reset the sitewide currency between tests (it persists via zustand).
  useUIStore.setState({ currency: 'USD' })
})

function withClient(ui: React.ReactElement, seed?: (qc: QueryClient) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seed?.(qc)
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('MarketCard (USD path)', () => {
  it('shows the market price label with selected finish', () => {
    withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil', 'foil']} onFinishChange={noop}
        delta1d={2.5} delta7d={-1.0} delta30d={5.0} />
    )
    expect(screen.getByText(/MARKET PRICE/i)).toBeInTheDocument()
  })

  it('renders the integer and cents portions of price', () => {
    withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil']} onFinishChange={noop}
        delta1d={0} delta7d={0} delta30d={0} />
    )
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText(/50/)).toBeInTheDocument()
  })

  it('renders N/A when price is null', () => {
    withClient(
      <MarketCard cardVersionId={CARD_ID} price={null} selectedFinish="nonfoil"
        finishes={['nonfoil']} onFinishChange={noop}
        delta1d={0} delta7d={0} delta30d={0} />
    )
    expect(screen.getByText('N/A')).toBeInTheDocument()
  })

  it('renders three deltas with absolute values', () => {
    withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil']} onFinishChange={noop}
        delta1d={2.5} delta7d={-1.0} delta30d={5.0} />
    )
    expect(screen.getByText(/2\.50/)).toBeInTheDocument()
    expect(screen.getByText(/1\.00/)).toBeInTheDocument()
    expect(screen.getByText(/5\.00/)).toBeInTheDocument()
  })

  it('uses up class for positive deltas and down class for negative deltas', () => {
    const { container } = withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil']} onFinishChange={noop}
        delta1d={2.5} delta7d={-1.0} delta30d={5.0} />
    )
    expect(container.querySelectorAll('[class*="up"]').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('[class*="down"]').length).toBeGreaterThan(0)
  })

  it('renders one button per finish', () => {
    withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil', 'foil']} onFinishChange={noop}
        delta1d={0} delta7d={0} delta30d={0} />
    )
    expect(screen.getByText('nonfoil')).toBeInTheDocument()
    expect(screen.getByText('foil')).toBeInTheDocument()
  })

  it('marks selected finish with aria-pressed=true', () => {
    withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil', 'foil']} onFinishChange={noop}
        delta1d={0} delta7d={0} delta30d={0} />
    )
    const selected = screen.getByRole('button', { pressed: true })
    expect(selected.textContent).toBe('nonfoil')
  })

  it('calls onFinishChange with the clicked finish', () => {
    const onFinishChange = vi.fn()
    withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil']} onFinishChange={onFinishChange}
        delta1d={0} delta7d={0} delta30d={0} />
    )
    fireEvent.click(screen.getByText('nonfoil'))
    expect(onFinishChange).toHaveBeenCalledWith('nonfoil')
  })
})

describe('MarketCard (non-USD path)', () => {
  it('derives spot price and 30d delta from the currency-scoped history series', () => {
    useUIStore.setState({ currency: 'EUR' })

    // 31-point dense daily series: index 0 = 8.00, the rest 10.00.
    // spot = latest non-null = 10.00; 30d delta = (10 - 8) / 8 * 100 = 25.00%.
    const series: (number | null)[] = Array(31).fill(10.0)
    series[0] = 8.0

    const { container } = withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil']} onFinishChange={noop}
        delta1d={1} delta7d={1} delta30d={1} />,
      (qc) => {
        const opts = cardPriceHistoryQueryOptions(CARD_ID, '3m', 'nonfoil', 'EUR')
        qc.setQueryData(opts.queryKey, {
          price_history_list_avg: series,
          price_history_sold_avg: Array(31).fill(null),
          date_range: { start: '2026-01-01', end: '2026-01-31', days_back: 90 },
        })
      }
    )

    // Spot shows the EUR-symboled latest value, not the USD prop (42.50).
    expect(container.textContent).toContain('€10')
    expect(container.textContent).not.toContain('42')
    // 30d delta derived from the series.
    expect(screen.getByText(/25\.00/)).toBeInTheDocument()
  })

  it('shows N/A when the currency has no history data', () => {
    useUIStore.setState({ currency: 'EUR' })
    // No seeded data → history undefined → spot null → N/A, never a USD fallback.
    const { container } = withClient(
      <MarketCard cardVersionId={CARD_ID} price={42.5} selectedFinish="nonfoil"
        finishes={['nonfoil']} onFinishChange={noop}
        delta1d={1} delta7d={1} delta30d={1} />
    )
    expect(screen.getByText('N/A')).toBeInTheDocument()
    expect(container.textContent).not.toContain('42')
  })
})
