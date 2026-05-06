// src/frontend/src/mocks/handlers.ts
import { http, HttpResponse } from 'msw'
import { MOCK_CARDS, MOCK_CARD_DETAIL } from './data'
import type { CardSearchResponse, CardSuggestResponse } from '../features/cards/types'
import {
  MOCK_AUTHORIZED_USERS,
  MOCK_PENDING_INVITES,
  MOCK_REVOKED_USERS,
  MOCK_AUDIT_LOG,
} from '../features/ebay/mockAuthorizedUsers'
import { MOCK_CONNECTED_STATUS } from '../features/ebay/mockEbayApp'

export const handlers = [
  // ── eBay credentials ────────────────────────────────────────────────────
  http.post('/api/ebay/credentials', async ({ request }) => {
    const body = await request.json()
    if (!body || typeof body !== 'object') {
      return new HttpResponse(null, { status: 400 })
    }
    return HttpResponse.json({ ok: true })
  }),

  http.post('/api/ebay/verify', async () => {
    // Simulate ~400ms latency then success
    await new Promise((r) => setTimeout(r, 400))
    return HttpResponse.json(MOCK_CONNECTED_STATUS)
  }),

  // ── eBay users ───────────────────────────────────────────────────────────
  http.get('/api/ebay/users', () => {
    return HttpResponse.json({
      active: MOCK_AUTHORIZED_USERS,
      pending: MOCK_PENDING_INVITES,
      revoked: MOCK_REVOKED_USERS,
      auditLog: MOCK_AUDIT_LOG,
    })
  }),

  http.post('/api/ebay/users/invite', async ({ request }) => {
    const body = await request.json()
    if (!body || typeof body !== 'object') {
      return new HttpResponse(null, { status: 400 })
    }
    return HttpResponse.json({ ok: true })
  }),

  http.delete('/api/ebay/users/:id', ({ params }) => {
    return HttpResponse.json({ ok: true, id: params.id })
  }),


  http.get('/api/catalog/mtg/card-reference/', ({ request }) => {
    const url = new URL(request.url)
    const q = (url.searchParams.get('q') ?? '').toLowerCase()
    const rarity = url.searchParams.get('rarity')
    const finish = url.searchParams.get('finish')

    let cards = MOCK_CARDS
    if (q) cards = cards.filter((c) => c.card_name.toLowerCase().includes(q))
    if (rarity) cards = cards.filter((c) => c.rarity_name === rarity)
    if (finish) cards = cards.filter((c) => c.finish === finish)

    const response: CardSearchResponse = {
      cards,
      total: cards.length,
      page: 1,
      per_page: 20,
    }
    return HttpResponse.json(response)
  }),

  http.get('/api/catalog/mtg/card-reference/suggest', ({ request }) => {
    const url = new URL(request.url)
    const q = (url.searchParams.get('q') ?? '').toLowerCase()
    const limit = parseInt(url.searchParams.get('limit') ?? '10', 10)

    let suggestions = MOCK_CARDS
    if (q) suggestions = suggestions.filter((c) => c.card_name.toLowerCase().includes(q))
    suggestions = suggestions.slice(0, limit)

    const response: CardSuggestResponse = {
      suggestions: suggestions.map((c) => ({
        card_version_id: c.card_version_id,
        card_name: c.card_name,
        set_code: c.set_code,
        collector_number: '1',
        rarity_name: c.rarity_name,
        scryfall_id: undefined,
        score: 1.0,
      })),
    }
    return HttpResponse.json(response)
  }),

  http.get('/api/catalog/mtg/card-reference/:id', ({ params }) => {
    const card = MOCK_CARD_DETAIL[params.id as string]
    if (!card) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json(card)
  }),
]
