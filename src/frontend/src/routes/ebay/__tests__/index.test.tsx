// src/frontend/src/routes/ebay/__tests__/index.test.tsx
import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

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
vi.mock('../../../features/ebay/components/QuotaStrip', () => ({
  QuotaStrip: () => <div data-testid="quota-strip">Daily API quota</div>,
}))

import * as HubModule from '../index'

const PageComponent = (HubModule as any).Route?.component ?? (HubModule as any).EbayHubPage

describe('EbayHubPage', () => {
  function renderPage() {
    if (!PageComponent) throw new Error('Could not find EbayHubPage component')
    return render(<PageComponent />)
  }

  it('renders page title "eBay Integration"', () => {
    renderPage()
    expect(screen.getByText('eBay Integration')).toBeTruthy()
  })

  it('renders subtitle "BYOA · production"', () => {
    renderPage()
    expect(screen.getByText('BYOA · production')).toBeTruthy()
  })

  it('renders Connected badge when status is connected', () => {
    renderPage()
    expect(screen.getByLabelText(/connected to ebay/i)).toBeTruthy()
  })

  it('does NOT show warning banner when connected', () => {
    renderPage()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('renders App Setup card linking to /ebay/setup', () => {
    renderPage()
    const link = screen.getByText('App Setup').closest('a')
    expect(link?.getAttribute('href')).toBe('/ebay/setup')
    expect(screen.getByText('Credentials & OAuth scopes')).toBeTruthy()
  })

  it('renders Users card linking to /ebay/share', () => {
    renderPage()
    const link = screen.getByText('Users').closest('a')
    expect(link?.getAttribute('href')).toBe('/ebay/share')
    expect(screen.getByText('Access control & invites')).toBeTruthy()
  })

  it('renders Listings card linking to /listings', () => {
    renderPage()
    const link = screen.getByText('Listings').closest('a')
    expect(link?.getAttribute('href')).toBe('/listings')
    expect(screen.getByText('Smart pricing & one-click listing')).toBeTruthy()
  })

  it('shows "Connection stats" section', () => {
    renderPage()
    expect(screen.getByRole('region', { name: /connection stats/i })).toBeTruthy()
  })

  it('shows status stat tile', () => {
    renderPage()
    expect(screen.getByText('Status')).toBeTruthy()
  })

  it('shows environment stat tile', () => {
    renderPage()
    expect(screen.getByText('Environment')).toBeTruthy()
  })

  it('shows token expires stat', () => {
    renderPage()
    expect(screen.getByText('Token expires')).toBeTruthy()
  })

  it('shows authorized users count stat', () => {
    renderPage()
    expect(screen.getByText('Authorized users')).toBeTruthy()
  })

  it('renders the QuotaStrip component', () => {
    renderPage()
    expect(screen.getByTestId('quota-strip')).toBeTruthy()
  })
})
