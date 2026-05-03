// src/frontend/src/features/cards/api.ts
import { queryOptions } from '@tanstack/react-query'
import { apiClient } from '../../lib/apiClient'
import type { CardDetail, CardSearchParams, CardSearchResponse, CardSuggestParams, CardSuggestResponse, CatalogStats } from './types'

export function cardSearchQueryOptions(params: CardSearchParams) {
  return queryOptions({
    queryKey: ['cards', 'search', params],
    queryFn: async () => {
      const qs = new URLSearchParams()
      if (params.q)        qs.set('q', params.q)
      if (params.set)      qs.set('set', params.set)
      if (params.rarity)   qs.set('rarity', params.rarity)
      if (params.finish)   qs.set('finish', params.finish)
      if (params.minPrice != null) qs.set('min_price', String(params.minPrice))
      if (params.maxPrice != null) qs.set('max_price', String(params.maxPrice))
      if (params.page)     qs.set('page', String(params.page))

      const response = await apiClient<any>(`/catalog/mtg/card-reference/?${qs}`)

      // apiClient extracts the 'data' field, so response here is the list of cards
      // We need to wrap it back into the expected format
      return {
        cards: Array.isArray(response) ? response : [],
        total: 0,
        page: 1,
        per_page: 20,
      } as CardSearchResponse
    },
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
