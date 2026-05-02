// src/frontend/src/mocks/handlers.ts
import { http, HttpResponse } from 'msw'
import { MOCK_CARDS, MOCK_CARD_DETAIL } from './data'
import type { CardSearchResponse } from '../features/cards/types'

export const handlers = [
  http.get('/api/v1/cards/search', ({ request }) => {
    const url = new URL(request.url)
    const q = (url.searchParams.get('q') ?? '').toLowerCase()
    const rarity = url.searchParams.get('rarity')
    const finish = url.searchParams.get('finish')

    let cards = MOCK_CARDS
    if (q) cards = cards.filter((c) => c.name.toLowerCase().includes(q))
    if (rarity) cards = cards.filter((c) => c.rarity === rarity)
    if (finish) cards = cards.filter((c) => c.finish === finish)

    const response: CardSearchResponse = {
      cards,
      total: cards.length,
      page: 1,
      per_page: 20,
    }
    return HttpResponse.json(response)
  }),

  http.get('/api/v1/cards/:id', ({ params }) => {
    const card = MOCK_CARD_DETAIL[params.id as string]
    if (!card) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json(card)
  }),
]
