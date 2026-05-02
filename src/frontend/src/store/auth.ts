// src/frontend/src/store/auth.ts
// Minimal stub — Task 4 (Zustand stores) will implement this fully.
// This file exists so the Vite import-analysis transform can resolve it;
// tests mock it via vi.mock('../../store/auth').

export interface AuthState {
  token: string | null
  logout: () => void
}

// Placeholder — replaced by the real Zustand store in Task 4
export const useAuthStore = {
  getState: (): AuthState => ({ token: null, logout: () => {} }),
}
