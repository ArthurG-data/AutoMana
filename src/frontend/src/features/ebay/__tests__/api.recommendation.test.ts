import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchRecommendation, stageAction, fetchPendingAction } from '../api'
import type { EbayLiveListing } from '../mockListings'

vi.mock('../../../lib/apiClient', () => ({
  apiClient: vi.fn(),
}))

import { apiClient } from '../../../lib/apiClient'

const mockApiClient = vi.mocked(apiClient)

const baseListing: EbayLiveListing = {
  itemId: 'item-001',
  title: 'Ragavan, Nimble Pilferer MH2 NM MTG',
  cardName: 'Ragavan, Nimble Pilferer',
  setCode: 'MH2',
  setInfo: 'MH2',
  price: 62,
  currency: 'AUD',
  conditionLabel: 'Near Mint',
  finish: 'Regular',
  style: '',
  daysListed: 14,
  watchCount: 3,
  viewItemUrl: 'https://www.ebay.com.au/itm/item-001',
  imageUrl: null,
  appCode: 'automana_au',
  appName: 'AutoMana AU',
}

describe('fetchRecommendation', () => {
  beforeEach(() => {
    mockApiClient.mockReset()
  })

  it('returns a ListingRecommendation with suggested_action on happy path', async () => {
    const mockRec = {
      item_id: 'item-001',
      suggested_action: 'raise' as const,
      strategy_kind: 'market_median',
      suggested_price: 68.0,
      confidence: 0.82,
      signals_used: 'market' as const,
      all_strategies: {
        market_median: { price: 68.0, description: 'Median of active listings', confidence: 0.82 },
      },
    }
    mockApiClient.mockResolvedValue(mockRec)

    const result = await fetchRecommendation('automana_au', baseListing)

    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/recommendations/item-001?app_code=automana_au',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result.suggested_action).toBe('raise')
    expect(result.item_id).toBe('item-001')
    expect(result.confidence).toBe(0.82)
  })
})

describe('stageAction', () => {
  beforeEach(() => {
    mockApiClient.mockReset()
  })

  it('returns StageActionResponse with created === true on happy path', async () => {
    mockApiClient.mockResolvedValue({ action_id: 'act-abc-123', created: true })

    const result = await stageAction('automana_au', 'item-001', {
      action_type: 'raise',
      strategy_kind: 'market_median',
      suggested_price: 68.0,
    })

    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/recommendations/item-001/stage?app_code=automana_au',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result.created).toBe(true)
    expect(result.action_id).toBe('act-abc-123')
  })
})

describe('fetchPendingAction', () => {
  beforeEach(() => {
    mockApiClient.mockReset()
  })

  it('returns null when response data is { pending: null }', async () => {
    mockApiClient.mockResolvedValue({ pending: null })

    const result = await fetchPendingAction('item-001')

    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/recommendations/item-001/pending',
    )
    expect(result).toBeNull()
  })
})
