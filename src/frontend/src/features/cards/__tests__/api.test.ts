// src/frontend/src/features/cards/__tests__/api.test.ts
import { describe, it, expect } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { cardSearchQueryOptions, cardDetailQueryOptions } from '../api'

describe('cardSearchQueryOptions', () => {
  it('returns cards from /api/v1/cards/search', async () => {
    const opts = cardSearchQueryOptions({ q: 'Ragavan' })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const data = await qc.fetchQuery(opts)
    expect(data.cards.length).toBeGreaterThan(0)
    expect(data.cards[0].name).toContain('Ragavan')
  })
})

describe('cardDetailQueryOptions', () => {
  it('returns card detail from /api/v1/cards/:id', async () => {
    const opts = cardDetailQueryOptions('ragavan-mh2')
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const data = await qc.fetchQuery(opts)
    expect(data.id).toBe('ragavan-mh2')
    expect(data.price_history.length).toBe(365)
  })

  it('throws on 404', async () => {
    const opts = cardDetailQueryOptions('does-not-exist')
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    await expect(qc.fetchQuery(opts)).rejects.toMatchObject({ status: 404 })
  })
})
