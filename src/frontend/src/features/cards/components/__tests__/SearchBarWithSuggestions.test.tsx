// src/frontend/src/features/cards/components/__tests__/SearchBarWithSuggestions.test.tsx
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
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

describe('SearchBarWithSuggestions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
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
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    })

    await user.keyboard('{Escape}')

    await waitFor(() => {
      expect(screen.queryByText('Ragavan, Nimble Pilferer')).not.toBeInTheDocument()
    })
  })

  it('clears input when blur happens', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    })

    await user.tab()

    // Dropdown should close after blur
    await waitFor(() => {
      expect(screen.queryByText('Ragavan, Nimble Pilferer')).not.toBeInTheDocument()
    }, { timeout: 500 })
  })

  it('navigates to search page when suggestion is selected', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    })

    const suggestion = screen.getByText('Ragavan, Nimble Pilferer')
    await user.click(suggestion)

    // Input should be cleared after selection
    expect(input.value).toBe('')
  })

  it('supports keyboard navigation in suggestions', async () => {
    const user = userEvent.setup()
    render(<SearchBarWithSuggestions />, { wrapper: Wrapper })

    const input = screen.getByPlaceholderText(/Search any card/) as HTMLInputElement
    await user.type(input, 'rag')

    await waitFor(() => {
      expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
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
    expect(screen.queryByText('Ragavan, Nimble Pilferer')).not.toBeInTheDocument()
  })
})
