// src/frontend/src/store/__tests__/auth.test.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '../auth'

describe('useAuthStore', () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, currentUser: null })
  })

  it('initialises unauthenticated', () => {
    expect(useAuthStore.getState().token).toBeNull()
    expect(useAuthStore.getState().currentUser).toBeNull()
  })

  it('login sets token and user', () => {
    useAuthStore.getState().login('real-token', { username: 'alice', email: 'u@test.com' })
    expect(useAuthStore.getState().token).toBe('real-token')
    expect(useAuthStore.getState().currentUser?.email).toBe('u@test.com')
    expect(useAuthStore.getState().currentUser?.username).toBe('alice')
  })

  it('logout clears token and user', () => {
    useAuthStore.getState().login('real-token', { username: 'alice', email: 'u@test.com' })
    useAuthStore.getState().logout()
    expect(useAuthStore.getState().token).toBeNull()
    expect(useAuthStore.getState().currentUser).toBeNull()
  })
})
