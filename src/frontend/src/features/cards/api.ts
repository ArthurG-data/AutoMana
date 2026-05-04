// src/frontend/src/features/cards/api.ts
import { queryOptions, infiniteQueryOptions } from '@tanstack/react-query'
import { apiClient } from '../../lib/apiClient'
import { useAuthStore } from '../../store/auth'
import type { CardDetail, CardSearchParams, CardSearchResponse, CardSuggestParams, CardSuggestResponse, CatalogStats } from './types'

export function cardInfiniteSearchQueryOptions(params: Omit<CardSearchParams, 'page'>) {
  return infiniteQueryOptions({
    queryKey: ['cards', 'search', params],
    queryFn: async ({ pageParam = 0 }) => {
      const token = useAuthStore.getState().token
      const qs = new URLSearchParams()
      if (params.q)        qs.set('q', params.q)
      if (params.set)      qs.set('set', params.set)
      if (params.rarity)   qs.set('rarity', params.rarity)
      if (params.finish)   qs.set('finish', params.finish)
      if (params.layout)   qs.set('layout', params.layout)
      if (params.minPrice != null) qs.set('min_price', String(params.minPrice))
      if (params.maxPrice != null) qs.set('max_price', String(params.maxPrice))
      qs.set('limit', '20')
      qs.set('offset', String(pageParam))

      const res = await fetch(`/api/catalog/mtg/card-reference/?${qs}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })

      if (!res.ok) throw new Error(`API ${res.status}`)
      const body = await res.json()

      return {
        cards: body.data ?? [],
        pagination: body.pagination,
      }
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.pagination?.has_next
        ? lastPage.pagination.offset + lastPage.pagination.limit
        : undefined,
  })
}

export function cardDetailQueryOptions(id: string) {
  return queryOptions({
    queryKey: ['cards', id],
    queryFn: () => apiClient<CardDetail>(`/catalog/mtg/card-reference/${id}`),
  })
}

export function cardSuggestQueryOptions(params: CardSuggestParams) {
  return queryOptions({
    queryKey: ['cards', 'suggest', params.q, params.limit],
    queryFn: () => {
      const qs = new URLSearchParams()
      qs.set('q', params.q)
      if (params.limit) qs.set('limit', String(params.limit))
      return apiClient<CardSuggestResponse>(`/catalog/mtg/card-reference/suggest?${qs}`)
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 10, // 10 minutes
  })
}

export function cardCatalogStatsQueryOptions() {
  return queryOptions({
    queryKey: ['cards', 'catalog-stats'],
    queryFn: () => apiClient<CatalogStats>('/catalog/mtg/card-reference/stats'),
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
    gcTime: 1000 * 60 * 60 * 24 * 2, // 48 hours
  })
}

export function cardPriceHistoryQueryOptions(
  cardId: string,
  range: '1w' | '1m' | '3m' | '1y' | 'all' = '1m'
) {
  return queryOptions({
    queryKey: ['cards', cardId, 'price-history', range],
    queryFn: async () => {
      const qs = new URLSearchParams()
      if (range !== '1m') qs.set('price_range', range)

      const res = await fetch(
        `/api/catalog/mtg/card-reference/${cardId}/price-history?${qs}`,
        { headers: { 'Content-Type': 'application/json' } }
      )
      if (!res.ok) throw new Error(`Failed to fetch price history: ${res.status}`)
      const json = await res.json()
      return json.data // ApiResponse wraps data
    },
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
    gcTime: 1000 * 60 * 60 * 24 * 7, // 7 days
  })
}
