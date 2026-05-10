import { describe, it, expect, beforeEach } from 'vitest'
import { server } from '../../../mocks/server'
import { http, HttpResponse } from 'msw'
import { cardInfiniteSearchQueryOptions } from '../api'
import { QueryClient } from '@tanstack/react-query'

const PROMO_RESPONSE = {
  success: true,
  data: [],
  pagination: { limit: 20, offset: 0, total_count: 0, has_next: false, has_previous: false },
  facets: { promo_types: ['buyabox', 'prerelease'] },
}

describe('cardInfiniteSearchQueryOptions — promo type', () => {
  let capturedUrl: string

  beforeEach(() => {
    capturedUrl = ''
    server.use(
      http.get('/api/catalog/mtg/card-reference/', ({ request }) => {
        capturedUrl = request.url
        return HttpResponse.json(PROMO_RESPONSE)
      })
    )
  })

  it('serializes promoTypes as repeated promo_type params', async () => {
    const qc = new QueryClient()
    const opts = cardInfiniteSearchQueryOptions({ promoTypes: ['buyabox', 'prerelease'] })
    await qc.fetchInfiniteQuery({ ...opts, initialPageParam: 0 })
    const url = new URL(capturedUrl)
    expect(url.searchParams.getAll('promo_type')).toEqual(['buyabox', 'prerelease'])
  })

  it('reads facets.promo_types from response', async () => {
    const qc = new QueryClient()
    const opts = cardInfiniteSearchQueryOptions({})
    const result = await qc.fetchInfiniteQuery({ ...opts, initialPageParam: 0 })
    expect(result.pages[0].facets?.promo_types).toEqual(['buyabox', 'prerelease'])
  })
})
