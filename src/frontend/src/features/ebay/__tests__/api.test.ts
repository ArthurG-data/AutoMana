import { describe, it, expect, vi, beforeEach } from 'vitest'
import { registerEbayApp, fetchActiveListings } from '../api'

vi.mock('../../../lib/apiClient', () => ({
  apiClient: vi.fn(),
}))

import { apiClient } from '../../../lib/apiClient'

const mockApiClient = vi.mocked(apiClient)

describe('registerEbayApp', () => {
  beforeEach(() => {
    mockApiClient.mockReset()
  })

  it('calls POST /integrations/ebay/auth/admin/apps with correct body', async () => {
    mockApiClient.mockResolvedValue({ message: 'eBay app registered successfully', app_code: 'cool_app_123' })

    const result = await registerEbayApp({
      app_name: 'My Store',
      description: 'Test app',
      environment: 'SANDBOX',
      ebay_app_id: 'MyApp-1234',
      client_secret: 'SBX-secret',
      redirect_uri: 'https://auth.automana.app/oauth/callback/ebay',
      allowed_scopes: ['https://api.ebay.com/oauth/api_scope/sell.inventory'],
    })

    expect(mockApiClient).toHaveBeenCalledWith('/integrations/ebay/auth/admin/apps', expect.objectContaining({ method: 'POST' }))
    const body = JSON.parse((mockApiClient.mock.calls[0][1] as RequestInit).body as string)
    expect(body).toEqual({
      app_name: 'My Store',
      description: 'Test app',
      environment: 'SANDBOX',
      ebay_app_id: 'MyApp-1234',
      client_secret: 'SBX-secret',
      redirect_uri: 'https://auth.automana.app/oauth/callback/ebay',
      allowed_scopes: ['https://api.ebay.com/oauth/api_scope/sell.inventory'],
      app_code: '',
      response_type: 'code',
      user_requirements: ['premium'],
    })
    expect(result.app_code).toBe('cool_app_123')
  })

  it('defaults app_code to empty string', async () => {
    mockApiClient.mockResolvedValue({ message: 'ok', app_code: 'auto_123' })

    await registerEbayApp({
      app_name: 'X',
      description: '',
      environment: 'PRODUCTION',
      ebay_app_id: 'id',
      client_secret: 'secret',
      redirect_uri: 'https://example.com',
      allowed_scopes: [],
    })

    const body = JSON.parse((mockApiClient.mock.calls[0][1] as RequestInit).body as string)
    expect(body.app_code).toBe('')
  })

  it('propagates errors from apiClient', async () => {
    mockApiClient.mockRejectedValue(new Error('API 403: forbidden'))
    await expect(
      registerEbayApp({
        app_name: 'X',
        description: '',
        environment: 'SANDBOX',
        ebay_app_id: 'id',
        client_secret: 'secret',
        redirect_uri: 'https://example.com',
        allowed_scopes: [],
      })
    ).rejects.toThrow('API 403: forbidden')
  })
})

describe('fetchActiveListings', () => {
  beforeEach(() => {
    mockApiClient.mockReset()
  })

  it('calls GET /listing/active with correct query params', async () => {
    mockApiClient.mockResolvedValue([])
    await fetchActiveListings('my_app', 50, 0)
    expect(mockApiClient).toHaveBeenCalledWith(
      '/listing/active?app_code=my_app&limit=50&offset=0'
    )
  })

  it('uses default limit=50 and offset=0', async () => {
    mockApiClient.mockResolvedValue([])
    await fetchActiveListings('my_app')
    expect(mockApiClient).toHaveBeenCalledWith(
      '/listing/active?app_code=my_app&limit=50&offset=0'
    )
  })

  it('maps StartPrice to price and currency', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '123',
        Title: 'Ragavan, Nimble Pilferer MH2 NM MTG',
        StartPrice: { currencyID: 'AUD', text: 62.0 },
        WatchCount: 5,
        ConditionDisplayName: 'Near Mint or Better',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/123' },
        PictureDetails: { GalleryURL: 'https://img.ebay.com/1.jpg' },
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].price).toBe(62)
    expect(result[0].currency).toBe('AUD')
    expect(result[0].itemId).toBe('123')
    expect(result[0].conditionLabel).toBe('Near Mint or Better')
  })

  it('falls back to ConditionDescription when ConditionDisplayName is absent', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '124',
        Title: 'Force of Will ALL LP MTG',
        StartPrice: { currencyID: 'AUD', text: 100 },
        WatchCount: 0,
        ConditionDescription: 'Light Play',
        ConditionDisplayName: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/124' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].conditionLabel).toBe('Light Play')
  })

  it('uses fallback eBay URL when ViewItemURL is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '456',
        Title: 'Force of Will ALL MTG',
        StartPrice: { currencyID: 'AUD', text: 10 },
        WatchCount: 0,
        ConditionDisplayName: null,
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: null,
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].viewItemUrl).toBe('https://www.ebay.com.au/itm/456')
  })

  it('extracts Finish from ItemSpecifics NameValueList (array)', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '789',
        Title: 'Ragavan, Nimble Pilferer MH2 NM FOIL MTG',
        StartPrice: { currencyID: 'AUD', text: 100 },
        WatchCount: 3,
        ConditionDisplayName: 'Near Mint',
        ConditionDescription: null,
        ItemSpecifics: {
          NameValueList: [{ Name: 'Finish', Value: 'Foil' }],
        },
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/789' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Foil')
  })

  it('extracts Finish from ItemSpecifics NameValueList (single object, not array)', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '790',
        Title: 'Ragavan MH2 NM FOIL MTG',
        StartPrice: { currencyID: 'AUD', text: 80 },
        WatchCount: 0,
        ConditionDisplayName: 'NM',
        ConditionDescription: null,
        ItemSpecifics: {
          NameValueList: { Name: 'Finish', Value: 'Foil' },
        },
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/790' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Foil')
  })

  it('defaults finish to Regular when ItemSpecifics is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '999',
        Title: 'Ancient Tomb TMP NM MTG',
        StartPrice: { currencyID: 'AUD', text: 58 },
        WatchCount: 0,
        ConditionDisplayName: 'NM',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/999' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Regular')
  })

  it('extracts GalleryURL when PictureDetails is present', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '111',
        Title: 'Dark Confidant RAV NM MTG',
        StartPrice: { currencyID: 'AUD', text: 30 },
        WatchCount: 1,
        ConditionDisplayName: 'NM',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/111' },
        PictureDetails: { GalleryURL: 'https://img.ebay.com/card.jpg' },
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].imageUrl).toBe('https://img.ebay.com/card.jpg')
  })

  it('sets imageUrl to null when PictureDetails is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '222',
        Title: 'Snapcaster Mage ISD LP MTG',
        StartPrice: { currencyID: 'AUD', text: 20 },
        WatchCount: 0,
        ConditionDisplayName: 'LP',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/222' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].imageUrl).toBeNull()
  })

  it('parses cardName from title', async () => {
    mockApiClient.mockResolvedValue([
      {
        ItemID: '333',
        Title: 'Sheoldred, the Apocalypse DMU #107 NM MTG',
        StartPrice: { currencyID: 'AUD', text: 44 },
        WatchCount: 0,
        ConditionDisplayName: 'NM',
        ConditionDescription: null,
        ItemSpecifics: null,
        ListingDetails: { ViewItemURL: 'https://www.ebay.com.au/itm/333' },
        PictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].cardName).toBe('Sheoldred, the Apocalypse')
    expect(result[0].setInfo).toBe('DMU #107')
  })

  it('propagates errors from apiClient', async () => {
    mockApiClient.mockRejectedValue(new Error('API 401: unauthorized'))
    await expect(fetchActiveListings('my_app')).rejects.toThrow('API 401: unauthorized')
  })
})
