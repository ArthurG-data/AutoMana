import { describe, it, expect } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '../../../../mocks/server'
import { PriceCharts } from '../PriceCharts'
import type { CardDetail } from '../../types'

const mockCard: CardDetail = {
  card_version_id: '11111111-1111-1111-1111-111111111111',
  card_name: 'Sheoldred',
  set_code: 'mom',
  set_name: 'March of the Machine',
  finish: 'non-foil',
  rarity_name: 'rare',
  price_change_1d: 0,
  price_change_7d: 0,
  price_change_30d: 0,
  image_uri: null,
  spark: [],
  available_finishes: ['nonfoil', 'foil'],
}

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider
    client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
  >
    {children}
  </QueryClientProvider>
)

describe('PriceCharts', () => {
  it('sends finish query param when finish prop is provided', async () => {
    let capturedFinish: string | null = null

    server.use(
      http.get('/api/catalog/mtg/card-reference/:id/price-history', ({ request }) => {
        capturedFinish = new URL(request.url).searchParams.get('finish')
        return HttpResponse.json({
          data: { price_history_list_avg: [], price_history_sold_avg: [] },
        })
      })
    )

    render(<PriceCharts card={mockCard} finish="foil" />, { wrapper: Wrapper })

    await waitFor(() => expect(capturedFinish).toBe('foil'))
  })

  it('omits finish query param when no finish prop is provided', async () => {
    let capturedFinish: string | null = 'sentinel'

    server.use(
      http.get('/api/catalog/mtg/card-reference/:id/price-history', ({ request }) => {
        capturedFinish = new URL(request.url).searchParams.get('finish')
        return HttpResponse.json({
          data: { price_history_list_avg: [], price_history_sold_avg: [] },
        })
      })
    )

    render(<PriceCharts card={mockCard} />, { wrapper: Wrapper })

    await waitFor(() => expect(capturedFinish).toBeNull())
  })
})
