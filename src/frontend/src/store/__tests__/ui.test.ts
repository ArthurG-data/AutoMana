// src/frontend/src/store/__tests__/ui.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock matchMedia before importing the store
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

import { useUIStore } from '../ui'

describe('useUIStore', () => {
  beforeEach(() => {
    useUIStore.setState({ theme: 'dark' })
    document.documentElement.dataset.theme = ''
  })

  it('defaults to dark theme', () => {
    expect(useUIStore.getState().theme).toBe('dark')
  })

  it('setTheme updates theme and data-theme attribute', () => {
    useUIStore.getState().setTheme('light')
    expect(useUIStore.getState().theme).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('toggleTheme flips dark → light', () => {
    useUIStore.getState().toggleTheme()
    expect(useUIStore.getState().theme).toBe('light')
  })

  it('toggleTheme flips light → dark', () => {
    useUIStore.setState({ theme: 'light' })
    useUIStore.getState().toggleTheme()
    expect(useUIStore.getState().theme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('')
  })
})
