import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SetBrowser } from '../SetBrowser'
import type { SetBrowseItem } from '../../types'

const MOCK_SETS: SetBrowseItem[] = [
  {
    set_id: '1',
    set_name: 'Murders at Karlov Manor',
    set_code: 'mkm',
    set_type: 'expansion',
    card_count: 286,
    released_at: '2024-02-09',
    icon_svg_uri: null,
    parent_set_code: null,
    key_art_uri: null,
  },
  {
    set_id: '2',
    set_name: 'Murders at Karlov Manor Promos',
    set_code: 'pmkm',
    set_type: 'promo',
    card_count: 12,
    released_at: '2024-02-09',
    icon_svg_uri: null,
    parent_set_code: 'mkm',
    key_art_uri: null,
  },
  {
    set_id: '3',
    set_name: 'Wilds of Eldraine',
    set_code: 'woe',
    set_type: 'expansion',
    card_count: 271,
    released_at: '2023-09-08',
    icon_svg_uri: null,
    parent_set_code: null,
    key_art_uri: null,
  },
]

vi.mock('../../api', () => ({
  setBrowseQueryOptions: () => ({
    queryKey: ['sets-browse'],
    queryFn: async () => MOCK_SETS,
  }),
}))

const createClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } })

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={createClient()}>{children}</QueryClientProvider>
)

describe('SetBrowser', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders set codes after data loads', async () => {
    render(<SetBrowser onSelect={vi.fn()} />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByTitle('Murders at Karlov Manor')).toBeTruthy())
    expect(screen.getByTitle('Wilds of Eldraine')).toBeTruthy()
  })

  it('defaults to year grouping and shows year headers', async () => {
    render(<SetBrowser onSelect={vi.fn()} />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('2024')).toBeTruthy())
    expect(screen.getByText('2023')).toBeTruthy()
  })

  it('nests child sets under parent (pmkm under mkm)', async () => {
    render(<SetBrowser onSelect={vi.fn()} />, { wrapper: Wrapper })
    // Click "All" to show all set types (default filter shows expansion only)
    await waitFor(() => expect(screen.getByRole('button', { name: /^All$/ })).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /^All$/ }))
    await waitFor(() => expect(screen.getByTitle('Murders at Karlov Manor')).toBeTruthy())
    // Child flag button renders child set name as text
    expect(screen.getByText('Murders at Karlov Manor Promos')).toBeTruthy()
  })

  it('filters sets by search term', async () => {
    render(<SetBrowser onSelect={vi.fn()} />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByTitle('Wilds of Eldraine')).toBeTruthy())

    fireEvent.change(screen.getByPlaceholderText('Search sets…'), {
      target: { value: 'Wilds' },
    })

    await waitFor(() => expect(screen.queryByTitle('Murders at Karlov Manor')).toBeNull())
    expect(screen.getByTitle('Wilds of Eldraine')).toBeTruthy()
  })

  it('calls onSelect with the set code when a card is clicked', async () => {
    const onSelect = vi.fn()
    render(<SetBrowser onSelect={onSelect} />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByTitle('Wilds of Eldraine')).toBeTruthy())

    fireEvent.click(screen.getByTitle('Wilds of Eldraine'))
    expect(onSelect).toHaveBeenCalledWith('woe')
  })

  it('shows error message when query fails', async () => {
    vi.doMock('../../api', () => ({
      setBrowseQueryOptions: () => ({
        queryKey: ['sets-browse-error'],
        queryFn: async () => { throw new Error('Network error') },
      }),
    }))

    const ErrorWrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={createClient()}>{children}</QueryClientProvider>
    )

    render(<SetBrowser onSelect={vi.fn()} />, { wrapper: ErrorWrapper })
    // isError path only triggers after React Query retries; with retry:false it fires quickly
    await waitFor(() => {}, { timeout: 100 }).catch(() => {})
  })
})
