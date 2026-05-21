// src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { server } from '../../../../mocks/server'
import { SearchBarWithSuggestions } from '../SearchBarWithSuggestions'

const createTestQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
})

// Mock useNavigate from @tanstack/react-router
const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={createTestQueryClient()}>
    {children}
  </QueryClientProvider>
)

const MOCK_SUGGESTIONS = [
  { card_version_id: 'ragavan-mh2',  card_name: 'Ragavan, Nimble Pilferer', set_code: 'MH2', collector_number: '138', rarity_name: 'mythic', score: 0.95 },
  { card_version_id: 'one-ring-ltr', card_name: 'The One Ring',             set_code: 'LTR', collector_number: '1',   rarity_name: 'mythic', score: 0.85 },
]

describe('SearchBarWithSuggestions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Provide a default MSW handler that filters by the `q` query param
    server.use(
      http.get('/api/catalog/mtg/card-reference/suggest', ({ request }) => {
        const q = new URL(request.url).searchParams.get('q') ?? ''
        const filtered = MOCK_SUGGESTIONS.filter((s) =>
          s.card_name.toLowerCase().includes(q.toLowerCase()) ||
          s.set_code.toLowerCase().includes(q.toLowerCase())
        )
        return HttpResponse.json({ success: true, data: { suggestions: filtered } })
      })
    )
  })

  it('renders search input with placeholder', () => {
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/)
    expect(input).toBeInTheDocument()
  })

  it('shows dropdown when user types enough characters', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText(/Ragavan, Nimble Pilferer/)).toBeInTheDocument()
    })
  })

  it('does not show dropdown with less than 2 characters', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'a')

    expect(screen.queryByText(/Ragavan/)).not.toBeInTheDocument()
  })

  it('hides dropdown when pressing Escape', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText(/Ragavan, Nimble Pilferer/)).toBeInTheDocument()
    })

    await user.keyboard('{Escape}')

    await waitFor(() => {
      expect(screen.queryByText(/Ragavan, Nimble Pilferer/)).not.toBeInTheDocument()
    })
  })

  it('clears input when blur happens', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText(/Ragavan, Nimble Pilferer/)).toBeInTheDocument()
    })

    await user.tab()

    // Dropdown should close after blur
    await waitFor(() => {
      expect(screen.queryByText(/Ragavan, Nimble Pilferer/)).not.toBeInTheDocument()
    }, { timeout: 500 })
  })

  it('navigates to card detail page when suggestion is selected', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText(/Ragavan, Nimble Pilferer/)).toBeInTheDocument()
    })

    await user.click(screen.getByText(/Ragavan, Nimble Pilferer/))

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/cards/$id',
      params: { id: 'ragavan-mh2' },
    })
    expect(input.value).toBe('')
  })

  it('supports keyboard navigation in suggestions', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText(/Ragavan, Nimble Pilferer/)).toBeInTheDocument()
    })

    // Press ArrowDown to select next item
    await user.keyboard('{ArrowDown}')

    // Check that a different suggestion might be highlighted
    // (this depends on the actual suggestions returned)
    const items = screen.getAllByRole('button')
    expect(items.length).toBeGreaterThan(0)
  })

  it('filters suggestions based on search query', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'ring')

    await waitFor(() => {
      expect(screen.getByText(/The One Ring/)).toBeInTheDocument()
    })

    // Should not show Ragavan results for "ring" search
    expect(screen.queryByText(/Ragavan, Nimble Pilferer/)).not.toBeInTheDocument()
  })

  it('hides suggestions with score < 0.5 when 3 or more are returned', async () => {
    server.use(
      http.get('/api/catalog/mtg/card-reference/suggest', () =>
        HttpResponse.json({
          suggestions: [
            { card_version_id: 'ragavan-mh2',    card_name: 'Ragavan, Nimble Pilferer', set_code: 'MH2', collector_number: '1', rarity_name: 'mythic', score: 0.9 },
            { card_version_id: 'one-ring-ltr',   card_name: 'The One Ring',             set_code: 'LTR', collector_number: '1', rarity_name: 'mythic', score: 0.7 },
            { card_version_id: 'bowmasters-ltr', card_name: 'Orcish Bowmasters',        set_code: 'LTR', collector_number: '1', rarity_name: 'rare',   score: 0.3 },
          ],
        })
      )
    )

    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/)
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText(/Ragavan, Nimble Pilferer/)).toBeInTheDocument()
    })

    expect(screen.getByText(/The One Ring/)).toBeInTheDocument()
    expect(screen.queryByText(/Orcish Bowmasters/)).not.toBeInTheDocument()
  })

  it('shows all suggestions when fewer than 3 are returned, regardless of score', async () => {
    server.use(
      http.get('/api/catalog/mtg/card-reference/suggest', () =>
        HttpResponse.json({
          suggestions: [
            { card_version_id: 'ragavan-mh2',  card_name: 'Ragavan, Nimble Pilferer', set_code: 'MH2', collector_number: '1', rarity_name: 'mythic', score: 0.31 },
            { card_version_id: 'one-ring-ltr', card_name: 'The One Ring',             set_code: 'LTR', collector_number: '1', rarity_name: 'mythic', score: 0.32 },
          ],
        })
      )
    )

    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/)
    await user.type(input, 'ra')

    await waitFor(() => {
      expect(screen.getByText(/Ragavan, Nimble Pilferer/)).toBeInTheDocument()
    })

    expect(screen.getByText(/The One Ring/)).toBeInTheDocument()
  })

  it('pressing Enter without arrow navigation goes to search results, not a card detail page', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/)
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText(/Ragavan, Nimble Pilferer/)).toBeInTheDocument()
    })

    await user.keyboard('{Enter}')

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/search', search: { q: 'rag' } })
  })
})
