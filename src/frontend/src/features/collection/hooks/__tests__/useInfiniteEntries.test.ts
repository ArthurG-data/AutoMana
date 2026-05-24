import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useInfiniteEntries } from '../useInfiniteEntries'
import * as api from '../../api'
import type { CollectionEntry } from '../../api'

const makeEntry = (id: string): CollectionEntry => ({
  item_id: id,
  card_version_id: 'cv1',
  card_name: 'Ragavan',
  set_code: 'MH2',
  collector_number: '138',
  finish: 'NONFOIL',
  condition: 'NM',
  purchase_price: '28.00',
  purchase_date: '2024-01-01',
  currency_code: 'USD',
  price: 30,
  price_change_1d: 0,
  status: 'purchased',
  is_wishlist: false,
})

describe('useInfiniteEntries', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('loads first page on mount', async () => {
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue([makeEntry('e1'), makeEntry('e2')])
    const { result } = renderHook(() => useInfiniteEntries('col1'))
    await waitFor(() => expect(result.current.allEntries).toHaveLength(2))
    expect(api.fetchEntriesPage).toHaveBeenCalledWith('col1', 0, expect.any(Number))
  })

  it('sets hasMore=false when page is smaller than limit', async () => {
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue([makeEntry('e1')])
    const { result } = renderHook(() => useInfiniteEntries('col1'))
    await waitFor(() => expect(result.current.hasMore).toBe(false))
  })

  it('sets hasMore=true when page equals limit', async () => {
    const fullPage = Array.from({ length: 50 }, (_, i) => makeEntry(`e${i}`))
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue(fullPage)
    const { result } = renderHook(() => useInfiniteEntries('col1'))
    await waitFor(() => expect(result.current.hasMore).toBe(true))
  })

  it('fetchNextPage appends entries and advances offset', async () => {
    const page1 = Array.from({ length: 50 }, (_, i) => makeEntry(`e${i}`))
    const page2 = [makeEntry('e50'), makeEntry('e51')]
    vi.spyOn(api, 'fetchEntriesPage')
      .mockResolvedValueOnce(page1)
      .mockResolvedValueOnce(page2)

    const { result } = renderHook(() => useInfiniteEntries('col1'))
    await waitFor(() => expect(result.current.allEntries).toHaveLength(50))

    await act(() => result.current.fetchNextPage())
    await waitFor(() => expect(result.current.allEntries).toHaveLength(52))
    expect(api.fetchEntriesPage).toHaveBeenCalledWith('col1', 50, expect.any(Number))
  })

  it('resets when collectionId changes', async () => {
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue([makeEntry('e1')])
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useInfiniteEntries(id),
      { initialProps: { id: 'col1' } },
    )
    await waitFor(() => expect(result.current.allEntries).toHaveLength(1))
    rerender({ id: 'col2' })
    await waitFor(() => expect(result.current.allEntries).toHaveLength(1))
    expect(api.fetchEntriesPage).toHaveBeenCalledWith('col2', 0, expect.any(Number))
  })

  it('calls fetchEntriesPage with isWishlist=false when specified', async () => {
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue([])
    renderHook(() => useInfiniteEntries('col-1', false))
    await waitFor(() => {
      expect(api.fetchEntriesPage).toHaveBeenCalledWith('col-1', 0, 50, false)
    })
  })

  it('calls fetchEntriesPage without isWishlist when not specified', async () => {
    vi.spyOn(api, 'fetchEntriesPage').mockResolvedValue([])
    renderHook(() => useInfiniteEntries('col-1'))
    await waitFor(() => {
      expect(api.fetchEntriesPage).toHaveBeenCalledWith('col-1', 0, 50, undefined)
    })
  })
})
