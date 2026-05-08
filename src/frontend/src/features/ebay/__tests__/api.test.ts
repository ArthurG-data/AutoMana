import { describe, it, expect, vi, beforeEach } from 'vitest'
import { registerEbayApp } from '../api'

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

    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/auth/admin/apps',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"app_name":"My Store"'),
      })
    )
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
