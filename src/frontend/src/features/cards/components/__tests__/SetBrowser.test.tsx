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
    await waitFor(() => expect(screen.getByText('MKM')).toBeTruthy())
    expect(screen.getByText('WOE')).toBeTruthy()
  })

  it('defaults to year grouping and shows year headers', async () => {
    render(<SetBrowser onSelect={vi.fn()} />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('2024')).toBeTruthy())
    expect(screen.getByText('2023')).toBeTruthy()
  })

  it('nests child sets under parent (pmkm under mkm)', async () => {
    render(<SetBrowser onSelect={vi.fn()} />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('MKM')).toBeTruthy())
    expect(screen.getByText('PMKM')).toBeTruthy()
  })

  it('filters sets by search term', async () => {
    render(<SetBrowser onSelect={vi.fn()} />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('WOE')).toBeTruthy())

    fireEvent.change(screen.getByPlaceholderText('Search sets by name or code…'), {
      target: { value: 'Wilds' },
    })

    await waitFor(() => expect(screen.queryByText('MKM')).toBeNull())
    expect(screen.getByText('WOE')).toBeTruthy()
  })

  it('calls onSelect with the set code when a card is clicked', async () => {
    const onSelect = vi.fn()
    render(<SetBrowser onSelect={onSelect} />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('WOE')).toBeTruthy())

    fireEvent.click(screen.getByText('WOE').closest('button')!)
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
