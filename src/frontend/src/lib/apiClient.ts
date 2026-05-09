// src/frontend/src/lib/apiClient.ts
import { useAuthStore } from '../store/auth'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Serialise concurrent 401 refresh attempts: all callers wait on the same
// in-flight promise rather than hammering the refresh endpoint in parallel.
let refreshPromise: Promise<string | null> | null = null

async function attemptTokenRefresh(): Promise<string | null> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    try {
      const res = await fetch('/api/users/auth/token/refresh', {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) return null
      const body = await res.json() as { access_token?: string }
      const newToken = body?.access_token ?? null
      if (newToken) useAuthStore.getState().login(newToken, useAuthStore.getState().currentUser!)
      return newToken
    } catch {
      return null
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

async function doFetch(path: string, token: string | null, options?: RequestInit): Promise<Response> {
  return fetch(`/api${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  })
}

export async function apiClient<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  let token = useAuthStore.getState().token
  let res = await doFetch(path, token, options)

  if (res.status === 401 && !path.includes('/auth/token')) {
    const newToken = await attemptTokenRefresh()
    if (newToken) {
      res = await doFetch(path, newToken, options)
    } else {
      useAuthStore.getState().logout()
    }
  }

  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${path}`, res.status)
  }

  const body = await res.json() as any

  // If response has a 'data' field, extract it (for wrapped API responses)
  if (body && typeof body === 'object' && 'data' in body && 'success' in body) {
    return body.data as T
  }

  return body as T
}
