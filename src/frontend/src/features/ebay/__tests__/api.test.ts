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

  it('calls GET /integrations/ebay/listing/active with correct query params', async () => {
    mockApiClient.mockResolvedValue([])
    await fetchActiveListings('my_app', 50, 0)
    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/listing/active?app_code=my_app&limit=50&offset=0'
    )
  })

  it('uses default limit=50 and offset=0', async () => {
    mockApiClient.mockResolvedValue([])
    await fetchActiveListings('my_app')
    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/listing/active?app_code=my_app&limit=50&offset=0'
    )
  })

  it('maps startPrice to price and currency', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '123',
        title: 'Ragavan, Nimble Pilferer MH2 NM MTG',
        startPrice: { currency: 'AUD', value: 62.0 },
        watchCount: 5,
        conditionDisplayName: 'Near Mint or Better',
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/123' },
        pictureDetails: { GalleryURL: 'https://img.ebay.com/1.jpg' },
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].price).toBe(62)
    expect(result[0].currency).toBe('AUD')
    expect(result[0].itemId).toBe('123')
    expect(result[0].conditionLabel).toBe('Near Mint or Better')
  })

  it('prefers buyItNowPrice over startPrice for fixed-price listings', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '125',
        title: 'Sheoldred DMU NM MTG',
        startPrice: { currency: 'AUD', value: 0 },
        buyItNowPrice: { currency: 'AUD', value: 44.0 },
        watchCount: 0,
        conditionDisplayName: 'NM',
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/125' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].price).toBe(44)
    expect(result[0].currency).toBe('AUD')
  })

  it('falls back conditionLabel to ebayConditionLabel when conditionID present', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '126',
        title: 'Force of Will ALL MTG',
        startPrice: { currency: 'AUD', value: 100 },
        watchCount: 0,
        conditionID: 3000,
        conditionDescription: null,
        conditionDisplayName: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/126' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].conditionLabel).toBe('Used')
  })

  it('extracts style from itemSpecifics Card Style field', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '127',
        title: 'Sheoldred DMU NM MTG',
        startPrice: { currency: 'AUD', value: 50 },
        watchCount: 0,
        conditionDisplayName: 'NM',
        conditionDescription: null,
        itemSpecifics: {
          NameValueList: [
            { Name: 'Finish', Value: 'Foil' },
            { Name: 'Card Style', Value: 'Extended Art' },
          ],
        },
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/127' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Foil')
    expect(result[0].style).toBe('Extended Art')
  })

  it('falls back to conditionDescription when conditionDisplayName is absent', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '124',
        title: 'Force of Will ALL LP MTG',
        startPrice: { currency: 'AUD', value: 100 },
        watchCount: 0,
        conditionDescription: 'Light Play',
        conditionDisplayName: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/124' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].conditionLabel).toBe('Light Play')
  })

  it('uses fallback eBay URL when viewItemUrl is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '456',
        title: 'Force of Will ALL MTG',
        startPrice: { currency: 'AUD', value: 10 },
        watchCount: 0,
        conditionDisplayName: null,
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: null,
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].viewItemUrl).toBe('https://www.ebay.com.au/itm/456')
  })

  it('extracts Finish from itemSpecifics NameValueList (array)', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '789',
        title: 'Ragavan, Nimble Pilferer MH2 NM FOIL MTG',
        startPrice: { currency: 'AUD', value: 100 },
        watchCount: 3,
        conditionDisplayName: 'Near Mint',
        conditionDescription: null,
        itemSpecifics: {
          NameValueList: [{ Name: 'Finish', Value: 'Foil' }],
        },
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/789' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Foil')
  })

  it('extracts Finish from itemSpecifics NameValueList (single object, not array)', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '790',
        title: 'Ragavan MH2 NM FOIL MTG',
        startPrice: { currency: 'AUD', value: 80 },
        watchCount: 0,
        conditionDisplayName: 'NM',
        conditionDescription: null,
        itemSpecifics: {
          NameValueList: { Name: 'Finish', Value: 'Foil' },
        },
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/790' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Foil')
  })

  it('defaults finish to Regular when itemSpecifics is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '999',
        title: 'Ancient Tomb TMP NM MTG',
        startPrice: { currency: 'AUD', value: 58 },
        watchCount: 0,
        conditionDisplayName: 'NM',
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/999' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].finish).toBe('Regular')
  })

  it('extracts GalleryURL when pictureDetails is present', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '111',
        title: 'Dark Confidant RAV NM MTG',
        startPrice: { currency: 'AUD', value: 30 },
        watchCount: 1,
        conditionDisplayName: 'NM',
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/111' },
        pictureDetails: { GalleryURL: 'https://img.ebay.com/card.jpg' },
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].imageUrl).toBe('https://img.ebay.com/card.jpg')
  })

  it('sets imageUrl to null when pictureDetails is null', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '222',
        title: 'Snapcaster Mage ISD LP MTG',
        startPrice: { currency: 'AUD', value: 20 },
        watchCount: 0,
        conditionDisplayName: 'LP',
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/222' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].imageUrl).toBeNull()
  })

  it('parses cardName, setCode and setInfo from title', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '333',
        title: 'Sheoldred, the Apocalypse DMU #107 NM MTG',
        startPrice: { currency: 'AUD', value: 44 },
        watchCount: 0,
        conditionDisplayName: 'NM',
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/333' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].cardName).toBe('Sheoldred, the Apocalypse')
    expect(result[0].setCode).toBe('DMU')
    expect(result[0].setInfo).toBe('DMU #107')
  })

  it('extracts finish and style from title when itemSpecifics absent', async () => {
    mockApiClient.mockResolvedValue([
      {
        itemID: '444',
        title: 'Ragavan, Nimble Pilferer Surge Foil Borderless MH2 NM MTG',
        startPrice: { currency: 'AUD', value: 80 },
        watchCount: 0,
        conditionDisplayName: 'NM',
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/444' },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].cardName).toBe('Ragavan, Nimble Pilferer')
    expect(result[0].setCode).toBe('MH2')
    expect(result[0].finish).toBe('Surge Foil')
    expect(result[0].style).toBe('Borderless')
  })

  it('calculates daysListed from listingDetails.startTime', async () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 86_400_000).toISOString()
    mockApiClient.mockResolvedValue([
      {
        itemID: '555',
        title: 'Force of Will ALL NM MTG',
        startPrice: { currency: 'AUD', value: 110 },
        watchCount: 0,
        conditionDisplayName: 'NM',
        conditionDescription: null,
        itemSpecifics: null,
        listingDetails: { viewItemUrl: 'https://www.ebay.com.au/itm/555', startTime: twoDaysAgo },
        pictureDetails: null,
      },
    ])
    const result = await fetchActiveListings('my_app')
    expect(result[0].daysListed).toBe(2)
  })

  it('propagates errors from apiClient', async () => {
    mockApiClient.mockRejectedValue(new Error('API 401: unauthorized'))
    await expect(fetchActiveListings('my_app')).rejects.toThrow('API 401: unauthorized')
  })
})
