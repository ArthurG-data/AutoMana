// src/frontend/src/store/auth.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface CurrentUser {
  id: string
  username: string
  email: string | null
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
      token: null,
      currentUser: null,
      login: (token, user) => set({ token, currentUser: user }),
      logout: () => set({ token: null, currentUser: null }),
    }),
    { name: 'automana-auth-v2' }
  )
)
