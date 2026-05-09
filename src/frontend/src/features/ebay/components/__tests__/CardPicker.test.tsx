import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { CardPicker } from '../CardPicker'
import type { CardSummary } from '../../../cards/types'

const mockCard: CardSummary = {
  card_version_id: 'cv1',
  card_name: 'Ragavan, Nimble Pilferer',
  set_code: 'mh2',
  set_name: 'Modern Horizons 2',
  finish: 'non-foil',
  rarity_name: 'mythic',
  price: 60,
  price_change_1d: 0,
  price_change_7d: 0,
  price_change_30d: 0,
  image_uri: null,
  image_normal: null,
  spark: [],
}

vi.mock('../../../cards/api', () => ({
  cardInfiniteSearchQueryOptions: (params: { q?: string }) => ({
    queryKey: ['cards', 'search', params],
    queryFn: async () => ({
      cards: [mockCard],
      pagination: { has_next: false, offset: 0, limit: 20, total_count: 1 },
    }),
    initialPageParam: 0,
    getNextPageParam: () => undefined,
  }),
}))

vi.mock('../../../cards/components/SearchResults', () => ({
  SearchResults: ({
    cards,
    onSelect,
    selectedId,
  }: {
    cards: CardSummary[]
    onSelect?: (c: CardSummary) => void
    selectedId?: string
  }) => (
    <div data-testid="search-results" data-selected-id={selectedId ?? ''}>
      {cards.map((c) => (
        <button key={c.card_version_id} onClick={() => onSelect?.(c)}>
          {c.card_name}
        </button>
      ))}
    </div>
  ),
}))

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('CardPicker', () => {
  it('renders a search input', () => {
    render(<CardPicker onSelect={vi.fn()} selectedId={undefined} />, { wrapper })
    expect(screen.getByPlaceholderText(/search cards/i)).toBeInTheDocument()
  })

  it('shows search results', async () => {
    render(<CardPicker onSelect={vi.fn()} selectedId={undefined} />, { wrapper })
    await waitFor(() => expect(screen.getByTestId('search-results')).toBeInTheDocument())
  })

  it('calls onSelect with the clicked card', async () => {
    const onSelect = vi.fn()
    render(<CardPicker onSelect={onSelect} selectedId={undefined} />, { wrapper })
    await waitFor(() => screen.getByText('Ragavan, Nimble Pilferer'))
    await userEvent.click(screen.getByText('Ragavan, Nimble Pilferer'))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ card_version_id: 'cv1' }))
  })

  it('forwards selectedId to SearchResults', async () => {
    render(<CardPicker onSelect={vi.fn()} selectedId="cv1" />, { wrapper })
    await waitFor(() => expect(screen.getByTestId('search-results')).toBeInTheDocument())
    expect(screen.getByTestId('search-results')).toHaveAttribute('data-selected-id', 'cv1')
  })
})
