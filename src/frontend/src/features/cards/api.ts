// src/frontend/src/features/cards/api.ts
import { queryOptions } from '@tanstack/react-query'
import { apiClient } from '../../lib/apiClient'
import type { CardDetail, CardSearchParams, CardSearchResponse } from './types'

export function cardSearchQueryOptions(params: CardSearchParams) {
  return queryOptions({
    queryKey: ['cards', 'search', params],
    queryFn: () => {
      const qs = new URLSearchParams()
      if (params.q)        qs.set('q', params.q)
      if (params.set)      qs.set('set', params.set)
      if (params.rarity)   qs.set('rarity', params.rarity)
      if (params.finish)   qs.set('finish', params.finish)
      if (params.minPrice != null) qs.set('min_price', String(params.minPrice))
      if (params.maxPrice != null) qs.set('max_price', String(params.maxPrice))
      if (params.page)     qs.set('page', String(params.page))
      return apiClient<CardSearchResponse>(`/cards/search?${qs}`)
    },
  })
}

export function cardDetailQueryOptions(id: string) {
  return queryOptions({
    queryKey: ['cards', id],
    queryFn: () => apiClient<CardDetail>(`/cards/${id}`),
  })
}
