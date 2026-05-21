// src/frontend/src/features/auth/api.ts
//
// Raw fetch wrappers for auth endpoints.
// Login uses application/x-www-form-urlencoded (OAuth2 password flow).
// Signup uses JSON. Neither goes through apiClient because login must not
// carry a Bearer token and must use a different Content-Type.

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface MeResponse {
  username: string
  fullname: string | null
}

/**
 * POST /api/users/auth/token
 * OAuth2 password-grant flow. Sends credentials as form-urlencoded.
 * The `username` field accepts either a username or an email (backend
 * falls back to email lookup when username lookup returns no match).
 */
export async function postLogin(email: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams({ username: email, password })
  const res = await fetch('/api/users/auth/token', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({})) as { detail?: string }
    throw Object.assign(new Error(detail.detail ?? 'Login failed'), { status: res.status })
  }
  return res.json() as Promise<LoginResponse>
}

/**
 * POST /api/users/
 * Registers a new account. The backend hashes the password on receipt.
 */
export async function postSignup(opts: {
  username: string
  email: string
  password: string
}): Promise<void> {
  const res = await fetch('/api/users/', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: opts.username,
      email: opts.email,
      password: opts.password,
    }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({})) as { detail?: string }
    throw Object.assign(new Error(detail.detail ?? 'Signup failed'), { status: res.status })
  }
}

/**
 * GET /api/users/me
 * Returns the authenticated user's profile. Requires a Bearer token.
 */
export async function getMe(token: string): Promise<MeResponse> {
  const res = await fetch('/api/users/me', {
    credentials: 'include',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw Object.assign(new Error('Failed to fetch profile'), { status: res.status })
  return res.json() as Promise<MeResponse>
}

/**
 * POST /api/users/auth/forgot-password
 * Always resolves (server returns 200 regardless of whether email exists).
 */
export async function postForgotPassword(email: string): Promise<void> {
  const res = await fetch('/api/users/auth/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({})) as { detail?: string }
    throw Object.assign(new Error(detail.detail ?? 'Request failed'), { status: res.status })
  }
}

/**
 * POST /api/users/auth/reset-password
 * token: raw token from the reset link query param
 * newPassword: the user's chosen new password (min 8 chars)
 */
export async function postResetPassword(token: string, newPassword: string): Promise<void> {
  const res = await fetch('/api/users/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({})) as { detail?: string }
    throw Object.assign(new Error(detail.detail ?? 'Reset failed'), { status: res.status })
  }
}
