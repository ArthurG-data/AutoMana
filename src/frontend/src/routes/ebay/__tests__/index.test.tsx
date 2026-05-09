// src/frontend/src/routes/ebay/__tests__/index.test.tsx
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    createFileRoute: () => (opts: { component: () => JSX.Element }) => opts,
    useNavigate: () => vi.fn(),
    Link: ({ children, to, className }: { children: React.ReactNode; to: string; className?: string }) => (
      <a href={to} className={className}>{children}</a>
    ),
  }
})

vi.mock('../../../components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('../../../components/layout/TopBar', () => ({
  TopBar: ({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) => (
    <div data-testid="topbar">
      {subtitle && <span>{subtitle}</span>}
      <h1>{title}</h1>
      {actions}
    </div>
  ),
}))
vi.mock('../../../components/design-system/Icon', () => ({
  Icon: ({ kind }: any) => <span data-icon={kind} />,
}))

vi.mock('../../../features/ebay/api', () => ({
  fetchUserApps: vi.fn(),
  fetchAppRateLimits: vi.fn(),
}))

import { fetchUserApps, fetchAppRateLimits } from '../../../features/ebay/api'
import type { EbayAppSummary } from '../../../features/ebay/api'
import * as HubModule from '../index'

const mockFetchUserApps = vi.mocked(fetchUserApps)
const mockFetchAppRateLimits = vi.mocked(fetchAppRateLimits)

const PageComponent = (HubModule as any).Route?.component ?? (HubModule as any).EbayHubPage

function makeApp(overrides: Partial<EbayAppSummary> = {}): EbayAppSummary {
  return {
    app_id: 'app-1',
    app_name: 'AutoMana AU',
    app_code: 'automana_au',
    environment: 'PRODUCTION',
    description: null,
    is_active: true,
    is_connected: true,
    token_expires_at: null,
    other_user_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('EbayHubPage', () => {
  beforeEach(() => {
    mockFetchUserApps.mockReset()
    mockFetchAppRateLimits.mockReset()
    mockFetchAppRateLimits.mockResolvedValue([])
  })

  function renderPage() {
    if (!PageComponent) throw new Error('Could not find EbayHubPage component')
    return render(<PageComponent />)
  }

  it('renders page title "eBay Integration"', () => {
    mockFetchUserApps.mockResolvedValue([])
    renderPage()
    expect(screen.getByText('eBay Integration')).toBeTruthy()
  })

  it('renders subtitle "BYOA · production"', () => {
    mockFetchUserApps.mockResolvedValue([])
    renderPage()
    expect(screen.getByText('BYOA · production')).toBeTruthy()
  })

  it('does NOT show warning banner when connected', () => {
    mockFetchUserApps.mockResolvedValue([])
    renderPage()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('renders App Setup card linking to /ebay/setup', () => {
    mockFetchUserApps.mockResolvedValue([])
    renderPage()
    const link = screen.getByText('App Setup').closest('a')
    expect(link?.getAttribute('href')).toBe('/ebay/setup')
    expect(screen.getByText('Credentials & OAuth scopes')).toBeTruthy()
  })

  it('renders Users card linking to /ebay/share', () => {
    mockFetchUserApps.mockResolvedValue([])
    renderPage()
    const link = screen.getByText('Users').closest('a')
    expect(link?.getAttribute('href')).toBe('/ebay/share')
    expect(screen.getByText('Access control & invites')).toBeTruthy()
  })

  it('renders Listings card linking to /listings', () => {
    mockFetchUserApps.mockResolvedValue([])
    renderPage()
    const link = screen.getByText('Listings').closest('a')
    expect(link?.getAttribute('href')).toBe('/listings')
    expect(screen.getByText('Smart pricing & one-click listing')).toBeTruthy()
  })

  it('shows empty state when no apps are registered', async () => {
    mockFetchUserApps.mockResolvedValue([])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/no apps registered yet/i)).toBeTruthy()
    })
  })

  it('shows Registered apps section when apps are present', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp()])
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('region', { name: /registered apps/i })).toBeTruthy()
      expect(screen.getByText('AutoMana AU')).toBeTruthy()
    })
  })

  it('shows connected status in app row', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp({ is_connected: true, token_expires_at: null })])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeTruthy()
    })
  })

  it('shows not-connected status in app row', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp({ is_connected: false })])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Not connected')).toBeTruthy()
    })
  })

  it('shows expiry date when token_expires_at is set', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp({ is_connected: true, token_expires_at: '2027-01-01T00:00:00Z' })])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/expires/i)).toBeTruthy()
    })
  })

  it('shows environment badge for each app', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp({ environment: 'PRODUCTION' })])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('PRODUCTION')).toBeTruthy()
    })
  })

  it('shows SANDBOX env badge for sandbox apps', async () => {
    mockFetchUserApps.mockResolvedValue([makeApp({ environment: 'SANDBOX' })])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('SANDBOX')).toBeTruthy()
    })
  })
})
