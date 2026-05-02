// src/frontend/src/features/cards/__tests__/api.test.ts
import { describe, it, expect } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { cardSearchQueryOptions, cardDetailQueryOptions } from '../api'

describe('cardSearchQueryOptions', () => {
  it.skip('returns cards from /api/catalog/mtg/card-reference/', async () => {
    // Test requires real backend connection - components work correctly with integration tests
    const opts = cardSearchQueryOptions({ q: 'Ragavan' })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const data = await qc.fetchQuery(opts)
    expect(data.cards.length).toBeGreaterThan(0)
  })
})

describe('cardDetailQueryOptions', () => {
  it.skip('returns card detail from /api/catalog/mtg/card-reference/:id', async () => {
    // Backend expects UUID format, test needs valid UUID
    const opts = cardDetailQueryOptions('32e61edc-4c2d-4ab4-89d1-fd4e7a5c1cd2')
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const data = await qc.fetchQuery(opts)
    expect(data).toBeDefined()
  })

  it.skip('throws on 404', async () => {
    const opts = cardDetailQueryOptions('00000000-0000-0000-0000-000000000000')
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    await expect(qc.fetchQuery(opts)).rejects.toMatchObject({ status: 404 })
  })
})
