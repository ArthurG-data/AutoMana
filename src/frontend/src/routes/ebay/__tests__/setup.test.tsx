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

// Mock the eBay API module
const mockRegisterEbayApp = vi.fn()
const mockStartEbayOAuth = vi.fn()
const mockVerifyEbayConnection = vi.fn()
const mockGetEbayCallbackUrl = vi.fn(() => 'http://localhost/api/integrations/ebay/auth/callback')

vi.mock('../../../features/ebay/api', () => ({
  registerEbayApp: (...args: unknown[]) => mockRegisterEbayApp(...args),
  startEbayOAuth: (...args: unknown[]) => mockStartEbayOAuth(...args),
  verifyEbayConnection: (...args: unknown[]) => mockVerifyEbayConnection(...args),
  getEbayCallbackUrl: () => mockGetEbayCallbackUrl(),
}))

// Stub clipboard API
const writeTextMock = vi.fn().mockResolvedValue(undefined)
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: writeTextMock },
  writable: true,
})

// Stub window.open
const windowOpenMock = vi.fn()
Object.defineProperty(window, 'open', { value: windowOpenMock, writable: true })

import { EbaySetupPage } from '../setup'

// Helper: fill credentials and advance to step 3 (scopes)
async function advanceToScopes() {
  render(<EbaySetupPage />)
  // step 0 → 1
  fireEvent.click(screen.getByRole('button', { name: /next/i }))
  fireEvent.change(screen.getByLabelText('App name'), { target: { value: 'MyApp' } })
  fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'test-app-id' } })
  fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'test-cert-id' } })
  // step 1 → 2
  fireEvent.click(screen.getByRole('button', { name: /next/i }))
  await waitFor(() => expect(screen.getByText('Configure OAuth scopes')).toBeTruthy())
}

describe('EbaySetupPage', () => {
  beforeEach(() => {
    writeTextMock.mockClear()
    windowOpenMock.mockClear()
    mockRegisterEbayApp.mockClear()
    mockStartEbayOAuth.mockClear()
    mockVerifyEbayConnection.mockClear()
    mockGetEbayCallbackUrl.mockClear()
    localStorage.clear()

    // Default resolved values for happy path
    mockRegisterEbayApp.mockResolvedValue({ app_code: 'test-app-code', message: 'ok' })
    mockStartEbayOAuth.mockResolvedValue({ authorization_url: 'https://ebay.com/oauth' })
    mockVerifyEbayConnection.mockResolvedValue({ expires_in: 3600, expires_on: '2026-06-01T00:00:00Z', scopes: [] })
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
    expect(screen.getByLabelText('App name')).toBeTruthy()
    expect(screen.getByLabelText('App ID (Client ID)')).toBeTruthy()
    expect(screen.getByLabelText('Cert ID (Client Secret)')).toBeTruthy()
  })

  it('does not render Dev ID field in Step 2', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.queryByLabelText('Dev ID')).toBeNull()
  })

  it('renders environment select in Step 2 with SANDBOX as default', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const envSelect = screen.getByLabelText('Environment') as HTMLSelectElement
    expect(envSelect).toBeTruthy()
    expect(envSelect.value).toBe('SANDBOX')
    expect(screen.getByRole('option', { name: 'SANDBOX' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'PRODUCTION' })).toBeTruthy()
  })

  it('shows validation errors on Step 2 when Next clicked with empty fields', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('App name is required')).toBeTruthy()
    expect(screen.getByText('App ID is required')).toBeTruthy()
    expect(screen.getByText('Cert ID is required')).toBeTruthy()
  })

  it('shows app name validation error but not dev ID error', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('App name is required')).toBeTruthy()
    expect(screen.queryByText('Dev ID is required')).toBeNull()
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
        expect.stringContaining('/api/integrations/ebay/auth/callback')
      )
    })
  })

  it('shows Redirect URI as read-only input', () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    const ruNameInput = document.getElementById('ebay-runame') as HTMLInputElement
    expect(ruNameInput.readOnly).toBe(true)
    expect(ruNameInput.value).toContain('/api/integrations/ebay/auth/callback')
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

  it('advances to Step 3 (scopes) when credentials are filled', async () => {
    render(<EbaySetupPage />)
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    fireEvent.change(screen.getByLabelText('App name'), { target: { value: 'MyApp' } })
    fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'test-app-id' } })
    fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'test-cert-id' } })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => expect(screen.getByText('Configure OAuth scopes')).toBeTruthy())
  })

  it('renders all OAuth scopes in Step 3', async () => {
    await advanceToScopes()
    expect(screen.getByText('sell.inventory')).toBeTruthy()
    expect(screen.getByText('sell.account')).toBeTruthy()
    expect(screen.getByText('sell.marketing')).toBeTruthy()
    expect(screen.getByText('sell.fulfillment')).toBeTruthy()
    expect(screen.getByText('buy.browse')).toBeTruthy()
    expect(screen.getByText('commerce.identity')).toBeTruthy()
  })

  it('shows REQUIRED badges on required scopes', async () => {
    await advanceToScopes()
    const badges = screen.getAllByText('REQUIRED')
    expect(badges.length).toBeGreaterThanOrEqual(5)
  })

  it('toggles non-required scope (sell.marketing)', async () => {
    await advanceToScopes()
    const marketingToggle = screen.getByRole('switch', { name: /toggle sell\.marketing/i })
    expect(marketingToggle.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(marketingToggle)
    expect(marketingToggle.getAttribute('aria-checked')).toBe('true')
  })

  it('does not toggle required scopes (sell.inventory stays on)', async () => {
    await advanceToScopes()
    const inventoryToggle = screen.getByRole('switch', { name: /toggle sell\.inventory/i })
    expect(inventoryToggle.getAttribute('aria-checked')).toBe('true')
    fireEvent.click(inventoryToggle)
    expect(inventoryToggle.getAttribute('aria-checked')).toBe('true')
  })

  it('calls registerEbayApp with correct payload when advancing from scopes to verify', async () => {
    await advanceToScopes()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => {
      expect(mockRegisterEbayApp).toHaveBeenCalledWith(
        expect.objectContaining({
          app_name: 'MyApp',
          description: 'MyApp',
          environment: 'SANDBOX',
          ebay_app_id: 'test-app-id',
          client_secret: 'test-cert-id',
          redirect_uri: 'http://localhost/api/integrations/ebay/auth/callback',
          allowed_scopes: expect.arrayContaining(['sell.inventory', 'sell.account']),
        })
      )
    })
  })

  it('advances to step 4 (verify) after successful registration', async () => {
    await advanceToScopes()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => expect(screen.getByText('Verify your connection')).toBeTruthy())
  })

  it('shows registration error when registerEbayApp fails', async () => {
    mockRegisterEbayApp.mockRejectedValueOnce(new Error('Invalid credentials'))
    await advanceToScopes()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => expect(screen.getByText('Invalid credentials')).toBeTruthy())
  })

  it('renders verify step with Authorize with eBay button', async () => {
    await advanceToScopes()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => expect(screen.getByText('Verify your connection')).toBeTruthy())
    expect(screen.getByRole('button', { name: /authorize with ebay/i })).toBeTruthy()
  })

  it('opens OAuth URL in new tab when Authorize button clicked', async () => {
    await advanceToScopes()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => screen.getByRole('button', { name: /authorize with ebay/i }))
    fireEvent.click(screen.getByRole('button', { name: /authorize with ebay/i }))
    await waitFor(() => {
      expect(mockStartEbayOAuth).toHaveBeenCalledWith('test-app-code')
      expect(windowOpenMock).toHaveBeenCalledWith('https://ebay.com/oauth', '_blank')
    })
  })

  it('shows verify connection button after OAuth is started', async () => {
    await advanceToScopes()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => screen.getByRole('button', { name: /authorize with ebay/i }))
    fireEvent.click(screen.getByRole('button', { name: /authorize with ebay/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /verify ebay connection/i })).toBeTruthy()
    )
  })

  it('calls verifyEbayConnection and updates status on verify', async () => {
    await advanceToScopes()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => screen.getByRole('button', { name: /authorize with ebay/i }))
    fireEvent.click(screen.getByRole('button', { name: /authorize with ebay/i }))
    await waitFor(() => screen.getByRole('button', { name: /verify ebay connection/i }))
    fireEvent.click(screen.getByRole('button', { name: /verify ebay connection/i }))
    await waitFor(() => {
      expect(mockVerifyEbayConnection).toHaveBeenCalledWith('test-app-code')
      expect(screen.getByText('Connection verified')).toBeTruthy()
      expect(localStorage.getItem('ebay_app_code')).toBe('test-app-code')
    })
  })

  it('shows OAuth error when startEbayOAuth fails', async () => {
    mockStartEbayOAuth.mockRejectedValueOnce(new Error('OAuth unavailable'))
    await advanceToScopes()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => screen.getByRole('button', { name: /authorize with ebay/i }))
    fireEvent.click(screen.getByRole('button', { name: /authorize with ebay/i }))
    await waitFor(() => expect(screen.getByText('OAuth unavailable')).toBeTruthy())
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
    expect(screen.getByText(/api quota/i)).toBeTruthy()
  })

  it('renders "Need help?" section with eBay developer portal link', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Need help?')).toBeTruthy()
    const link = screen.getByText('eBay Developer Portal')
    expect(link.closest('a')?.getAttribute('href')).toContain('developer.ebay.com')
  })
})
