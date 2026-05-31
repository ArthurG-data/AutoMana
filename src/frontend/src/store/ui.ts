// src/frontend/src/store/ui.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'dark' | 'light'

// Sitewide display currency. USD/EUR are live today; CAD/JPY are typed ahead of
// their price data being ingested so the UI can enable them with zero churn.
export type CurrencyCode = 'USD' | 'EUR' | 'CAD' | 'JPY'

interface UIState {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  currency: CurrencyCode
  setCurrency: (currency: CurrencyCode) => void
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme === 'light' ? 'light' : ''
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      theme: 'dark',
      setTheme: (theme) => {
        applyTheme(theme)
        set({ theme })
      },
      toggleTheme: () => {
        const next = get().theme === 'dark' ? 'light' : 'dark'
        applyTheme(next)
        set({ theme: next })
      },
      currency: 'USD',
      setCurrency: (currency) => set({ currency }),
    }),
    {
      name: 'automana-ui',
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme)
      },
    }
  )
)
