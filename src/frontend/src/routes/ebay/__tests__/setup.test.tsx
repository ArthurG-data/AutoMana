// src/frontend/src/routes/ebay/__tests__/setup.test.tsx
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock TanStack Router — createFileRoute is called at module load time
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    createFileRoute: (_path: string) => (opts: unknown) => opts,
    useNavigate: () => vi.fn(),
  }
})

// Mock layout components to avoid router/store context
vi.mock('../../../components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div data-testid="app-shell">{children}</div>,
}))
vi.mock('../../../components/layout/TopBar', () => ({
  TopBar: ({ title, subtitle, breadcrumb }: { title: string; subtitle?: string; breadcrumb?: string }) => (
    <div data-testid="topbar">
      {breadcrumb && <span>{breadcrumb}</span>}
      {subtitle && <span>{subtitle}</span>}
      <h1>{title}</h1>
    </div>
  ),
}))

// Stub clipboard API
const writeTextMock = vi.fn().mockResolvedValue(undefined)
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: writeTextMock },
  writable: true,
})

import { EbaySetupPage } from '../setup'

describe('EbaySetupPage', () => {
  beforeEach(() => {
    writeTextMock.mockClear()
  })

  it('renders page title', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Connect your eBay app')).toBeTruthy()
  })

  it('renders breadcrumb and subtitle', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Settings / Integrations')).toBeTruthy()
    expect(screen.getByText('eBay Developer')).toBeTruthy()
  })

  it('renders all 4 stepper steps', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Create app')).toBeTruthy()
    expect(screen.getByText('Paste keys')).toBeTruthy()
    expect(screen.getByText('OAuth scopes')).toBeTruthy()
    expect(screen.getByText('Verify')).toBeTruthy()
  })

  it('shows Step 1 (Create app) content by default', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Create your eBay app')).toBeTruthy()
    expect(screen.getByText(/developer.ebay.com/)).toBeTruthy()
  })

  it('advances to Step 2 (credentials) when Next is clicked', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByLabelText('App ID (Client ID)')).toBeTruthy()
    expect(screen.getByLabelText('Cert ID (Client Secret)')).toBeTruthy()
    expect(screen.getByLabelText('Dev ID')).toBeTruthy()
  })

  it('shows validation errors on Step 2 when Next clicked with empty fields', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('App ID is required')).toBeTruthy()
    expect(screen.getByText('Cert ID is required')).toBeTruthy()
    expect(screen.getByText('Dev ID is required')).toBeTruthy()
  })

  it('allows navigating back from Step 2', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(screen.getByText('Create your eBay app')).toBeTruthy()
  })

  it('copies Redirect URI to clipboard when copy button clicked', async () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const copyBtn = screen.getByRole('button', { name: /copy redirect uri/i })
    fireEvent.click(copyBtn)
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(
        expect.stringContaining('automana.app')
      )
    })
  })

  it('shows Redirect URI as read-only input', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const ruNameInput = screen.getByLabelText(/redirect uri/i) as HTMLInputElement
    expect(ruNameInput.readOnly).toBe(true)
    expect(ruNameInput.value).toContain('automana.app')
  })

  it('shows Cert ID input as password (masked) by default', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const certInput = screen.getByLabelText('Cert ID (Client Secret)') as HTMLInputElement
    expect(certInput.type).toBe('password')
  })

  it('reveals Cert ID when eye button is clicked', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const certInput = screen.getByLabelText('Cert ID (Client Secret)') as HTMLInputElement
    const revealBtn = screen.getByRole('button', { name: /show cert id/i })
    fireEvent.click(revealBtn)
    expect(certInput.type).toBe('text')
  })

  it('advances to Step 3 (scopes) when credentials are filled', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'test-app-id' } })
    fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'test-cert-id' } })
    fireEvent.change(screen.getByLabelText('Dev ID'), { target: { value: 'test-dev-id' } })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('Configure OAuth scopes')).toBeTruthy()
  })

  it('renders all OAuth scopes in Step 3', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'a' } })
    fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'b' } })
    fireEvent.change(screen.getByLabelText('Dev ID'), { target: { value: 'c' } })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('sell.inventory')).toBeTruthy()
    expect(screen.getByText('sell.account')).toBeTruthy()
    expect(screen.getByText('sell.marketing')).toBeTruthy()
    expect(screen.getByText('sell.fulfillment')).toBeTruthy()
    expect(screen.getByText('buy.browse')).toBeTruthy()
    expect(screen.getByText('commerce.identity')).toBeTruthy()
  })

  it('shows REQUIRED badges on required scopes', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'a' } })
    fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'b' } })
    fireEvent.change(screen.getByLabelText('Dev ID'), { target: { value: 'c' } })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const badges = screen.getAllByText('REQUIRED')
    expect(badges.length).toBeGreaterThanOrEqual(5)
  })

  it('toggles non-required scope (sell.marketing)', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'a' } })
    fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'b' } })
    fireEvent.change(screen.getByLabelText('Dev ID'), { target: { value: 'c' } })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const marketingToggle = screen.getByRole('switch', { name: /toggle sell\.marketing/i })
    expect(marketingToggle.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(marketingToggle)
    expect(marketingToggle.getAttribute('aria-checked')).toBe('true')
  })

  it('does not toggle required scopes (sell.inventory stays on)', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'a' } })
    fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'b' } })
    fireEvent.change(screen.getByLabelText('Dev ID'), { target: { value: 'c' } })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const inventoryToggle = screen.getByRole('switch', { name: /toggle sell\.inventory/i })
    expect(inventoryToggle.getAttribute('aria-checked')).toBe('true')
    fireEvent.click(inventoryToggle)
    // Should still be true (required scope, no onToggle handler)
    expect(inventoryToggle.getAttribute('aria-checked')).toBe('true')
  })

  it('renders verify step with test connection button', () => {
    render(<EbaySetupPage />)
    // step 1 → 2
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'a' } })
    fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'b' } })
    fireEvent.change(screen.getByLabelText('Dev ID'), { target: { value: 'c' } })
    // step 2 → 3
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    // step 3 → 4
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('Verify your connection')).toBeTruthy()
    expect(screen.getByRole('button', { name: /test ebay connection/i })).toBeTruthy()
  })

  it('renders sidebar with not connected status', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Connection status')).toBeTruthy()
    expect(screen.getByText('Not connected')).toBeTruthy()
  })

  it('renders sidebar connection metrics', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Environment')).toBeTruthy()
    expect(screen.getByText('Last verified')).toBeTruthy()
    expect(screen.getByText('Token expires')).toBeTruthy()
    expect(screen.getByText('Daily quota')).toBeTruthy()
    expect(screen.getByText('5,000')).toBeTruthy()
  })

  it('renders "Why bring your own app?" section', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText("Why bring your own app?")).toBeTruthy()
    // At least one benefit bullet
    expect(screen.getByText(/api quota/i)).toBeTruthy()
  })

  it('renders "Need help?" section with eBay developer portal link', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Need help?')).toBeTruthy()
    const link = screen.getByText('eBay Developer Portal')
    expect(link.closest('a')?.getAttribute('href')).toContain('developer.ebay.com')
  })
})
