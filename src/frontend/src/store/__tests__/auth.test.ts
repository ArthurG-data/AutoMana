// src/frontend/src/store/__tests__/auth.test.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '../auth'

describe('useAuthStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: 'dev-stub-token',
      currentUser: { id: 'dev', email: 'dev@automana.local' },
    })
  })

  it('initialises with stub token', () => {
    expect(useAuthStore.getState().token).toBe('dev-stub-token')
  })

  it('login sets token and user', () => {
    useAuthStore.getState().login('real-token', { id: 'u1', email: 'u@test.com' })
    expect(useAuthStore.getState().token).toBe('real-token')
    expect(useAuthStore.getState().currentUser?.email).toBe('u@test.com')
  })

  it('logout clears token and user', () => {
    useAuthStore.getState().logout()
    expect(useAuthStore.getState().token).toBeNull()
    expect(useAuthStore.getState().currentUser).toBeNull()
  })
})
