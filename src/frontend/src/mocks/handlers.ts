// src/frontend/src/mocks/handlers.ts
import { http, HttpResponse, passthrough } from 'msw'
import { MOCK_CARD_DETAIL } from './data'
import {
  MOCK_AUTHORIZED_USERS,
  MOCK_PENDING_INVITES,
  MOCK_REVOKED_USERS,
  MOCK_AUDIT_LOG,
} from '../features/ebay/mockAuthorizedUsers'
import { MOCK_CONNECTED_STATUS } from '../features/ebay/mockEbayApp'

export const handlers = [
  // ── AI chat ─────────────────────────────────────────────────────────────
  http.post('/api/integrations/ai/chat', async ({ request }) => {
    const body = await request.json() as { message: string; session_id?: string }
    const sessionId = body.session_id && body.session_id !== '' ? body.session_id : 'mock-session-123'
    return HttpResponse.json({
      success: true,
      data: {
        reply: `Mock reply for: ${body.message}`,
        session_id: sessionId,
        tools_called: [],
      },
    })
  }),

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


  http.get('/api/catalog/mtg/card-reference/', () => passthrough()),
  http.get('/api/catalog/mtg/card-reference/suggest', () => passthrough()),
  http.get('/api/catalog/mtg/card-reference/stats', () => passthrough()),
  http.get('/api/catalog/mtg/card-reference/:id/price-history', () => passthrough()),
  http.get('/api/catalog/mtg/card-reference/:id', ({ params }) => {
    const card = MOCK_CARD_DETAIL[params.id as string]
    if (card) return HttpResponse.json(card)
    return passthrough()
  }),
]
