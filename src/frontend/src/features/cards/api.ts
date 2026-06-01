// src/frontend/src/features/cards/api.ts
import { queryOptions, infiniteQueryOptions } from '@tanstack/react-query'
import { apiClient } from '../../lib/apiClient'
import { useAuthStore } from '../../store/auth'
import type { CardDetail, CardSearchParams, CardSearchResponse, CardSuggestParams, CardSuggestResponse, CatalogStats, SetBrowseItem, CardVersionRow, OtherSetRow } from './types'
import type { CurrencyCode } from '../../store/ui'

export function cardInfiniteSearchQueryOptions(params: Omit<CardSearchParams, 'page'>) {
  const { group: _group, ...apiParams } = params
  return infiniteQueryOptions({
    queryKey: ['cards', 'search', apiParams],
    queryFn: async ({ pageParam = 0 }) => {
      const token = useAuthStore.getState().token
      const qs = new URLSearchParams()
      if (params.q)              qs.set('q', params.q)
      if (params.set)            qs.set('set', params.set)
      if (params.artist)         qs.set('artist', params.artist)
      if (params.unique_card_id) qs.set('unique_card_id', params.unique_card_id)
      if (params.rarity)         qs.set('rarity', params.rarity)
      if (params.finish)   qs.set('finish', params.finish)
      if (params.layout)   qs.set('layout', params.layout)
      if (params.minPrice != null) qs.set('min_price', String(params.minPrice))
      if (params.maxPrice != null) qs.set('max_price', String(params.maxPrice))
      params.promoTypes?.forEach(pt => qs.append('promo_type', pt))
      if (params.sort_by)    qs.set('sort_by', params.sort_by)
      if (params.sort_order) qs.set('sort_order', params.sort_order)
      params.colors?.forEach(c => qs.append('color', c))
      if (params.card_type)  qs.set('card_type', params.card_type)
      params.frame_effects?.forEach(fe => qs.append('frame_effect', fe))
      if (params.collapse !== false) qs.set('collapse', 'true')
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
        facets: (body.facets as { promo_types?: string[]; rarities?: string[] } | null) ?? null,
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

export function setBrowseQueryOptions() {
  return queryOptions({
    queryKey: ['sets', 'browse'],
    queryFn: () => apiClient<SetBrowseItem[]>('/catalog/mtg/set-reference/browse'),
    staleTime: 1000 * 60 * 60,
    gcTime: 1000 * 60 * 60 * 24,
  })
}

export function cardVersionsInSetQueryOptions(uniqueCardId: string, setCode: string) {
  return queryOptions({
    queryKey: ['cards', 'versions-in-set', uniqueCardId, setCode],
    queryFn: async () => {
      const qs = new URLSearchParams({ unique_card_id: uniqueCardId, set_code: setCode })
      const res = await fetch(`/api/catalog/mtg/card-reference/versions-in-set?${qs}`, {
        headers: { 'Content-Type': 'application/json' },
      })
      if (!res.ok) throw new Error(`Failed to fetch versions: ${res.status}`)
      const json = await res.json()
      return (json.data ?? []) as CardVersionRow[]
    },
    staleTime: 1000 * 60 * 30,
    enabled: !!uniqueCardId && !!setCode,
  })
}

export function cardOtherSetsQueryOptions(uniqueCardId: string) {
  return queryOptions({
    queryKey: ['cards', 'other-sets', uniqueCardId],
    queryFn: async () => {
      const qs = new URLSearchParams({ unique_card_id: uniqueCardId })
      const res = await fetch(`/api/catalog/mtg/card-reference/other-sets?${qs}`, {
        headers: { 'Content-Type': 'application/json' },
      })
      if (!res.ok) throw new Error(`Failed to fetch other sets: ${res.status}`)
      const json = await res.json()
      return (json.data ?? []) as OtherSetRow[]
    },
    staleTime: 1000 * 60 * 30,
    enabled: !!uniqueCardId,
  })
}

export function cardPriceHistoryQueryOptions(
  cardId: string,
  range: '1w' | '1m' | '3m' | '1y' | 'all' = '1m',
  finish?: string,
  currency: CurrencyCode = 'USD'
) {
  return queryOptions({
    queryKey: ['cards', cardId, 'price-history', range, finish ?? 'all', currency],
    queryFn: async () => {
      const qs = new URLSearchParams({ price_range: range, currency })
      if (finish) qs.set('finish', finish)

      const res = await fetch(
        `/api/catalog/mtg/card-reference/${cardId}/price-history?${qs}`,
        { headers: { 'Content-Type': 'application/json' } }
      )
      if (!res.ok) throw new Error(`Failed to fetch price history: ${res.status}`)
      const json = await res.json()
      return json.data
    },
    staleTime: 1000 * 60 * 60 * 24,
    gcTime: 1000 * 60 * 60 * 24 * 7,
  })
}

