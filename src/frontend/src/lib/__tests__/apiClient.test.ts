// src/frontend/src/lib/__tests__/apiClient.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiClient, ApiError } from '../apiClient'
import { useAuthStore } from '../../store/auth'

// We mock the auth store — getState is a vi.fn() so individual tests can override it
vi.mock('../../store/auth', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({ token: 'test-token-123' })),
  },
}))

describe('apiClient', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    // Restore default: token present
    vi.mocked(useAuthStore.getState).mockReturnValue({ token: 'test-token-123' })
  })

  it('includes Authorization header with token', async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)

    await apiClient('/cards/search')

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/cards/search',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token-123',
        }),
      })
    )
  })

  it('throws ApiError with status on non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
    ))

    await expect(apiClient('/cards/missing')).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && e.status === 404
    )
  })

  it('omits Authorization header when token is null', async () => {
    vi.mocked(useAuthStore.getState).mockReturnValue({ token: null })
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )
    vi.stubGlobal('fetch', mockFetch)

    await apiClient('/public/endpoint')

    const [, options] = mockFetch.mock.calls[0] as [string, RequestInit & { headers?: Record<string, string> }]
    expect(options?.headers?.['Authorization']).toBeUndefined()
  })
})
