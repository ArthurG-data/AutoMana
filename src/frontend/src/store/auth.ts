// src/frontend/src/store/auth.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface CurrentUser {
  id: string
  email: string
}

interface AuthState {
  token: string | null
  currentUser: CurrentUser | null
  login: (token: string, user: CurrentUser) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: 'dev-stub-token',
      currentUser: { id: 'dev', email: 'dev@automana.local' },
      login: (token, user) => set({ token, currentUser: user }),
      logout: () => set({ token: null, currentUser: null }),
    }),
    { name: 'automana-auth' }
  )
)
