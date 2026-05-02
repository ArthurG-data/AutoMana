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

export async function apiClient<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const token = useAuthStore.getState().token

  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  })

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
