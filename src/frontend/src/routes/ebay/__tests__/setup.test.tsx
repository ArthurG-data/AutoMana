// src/frontend/src/routes/ebay/__tests__/setup.test.tsx
import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    createFileRoute: (_path: string) => (opts: unknown) => opts,
    useNavigate: () => vi.fn(),
  }
})

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

vi.mock('../../../features/ebay/api', () => ({
  registerEbayApp: vi.fn().mockResolvedValue({
    message: 'eBay app registered successfully',
    app_code: 'cool_app_123',
  }),
  startEbayOAuth: vi.fn().mockResolvedValue({ authorization_url: 'https://auth.ebay.com/oauth/authorize?test=1' }),
}))

import { registerEbayApp, startEbayOAuth } from '../../../features/ebay/api'
const mockRegisterEbayApp = vi.mocked(registerEbayApp)
const mockStartEbayOAuth = vi.mocked(startEbayOAuth)

const writeTextMock = vi.fn().mockResolvedValue(undefined)
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: writeTextMock },
  writable: true,
})

import { EbaySetupPage } from '../setup'

// Helper: navigate to Step 2 (credentials)
function goToStep2() {
  render(<EbaySetupPage />)
  fireEvent.click(screen.getByRole('button', { name: /next/i }))
}

// Helper: fill credentials and advance to Step 3 (scopes)
function goToStep3() {
  goToStep2()
  fireEvent.change(screen.getByLabelText('App Name'), { target: { value: 'My Store' } })
  fireEvent.change(screen.getByLabelText('App ID (Client ID)'), { target: { value: 'test-app-id' } })
  fireEvent.change(screen.getByLabelText('Cert ID (Client Secret)'), { target: { value: 'test-cert-id' } })
  fireEvent.change(screen.getByLabelText('RuName'), { target: { value: 'MyApp-MyApp-PRD-ab1234567-89abcdef' } })
  fireEvent.click(screen.getByRole('button', { name: /next/i }))
}

// Helper: advance through all steps to Step 4 (result screen)
async function goToStep4() {
  goToStep3()
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /register app/i }))
  })
  await waitFor(() => {
    expect(screen.getByText('App registered successfully')).toBeTruthy()
  })
}

describe('EbaySetupPage', () => {
  beforeEach(() => {
    writeTextMock.mockClear()
    mockRegisterEbayApp.mockReset()
    mockRegisterEbayApp.mockResolvedValue({
      message: 'eBay app registered successfully',
      app_code: 'cool_app_123',
    })
    mockStartEbayOAuth.mockReset()
    mockStartEbayOAuth.mockResolvedValue({ authorization_url: 'https://auth.ebay.com/oauth/authorize?test=1' })
    Object.defineProperty(window, 'location', {
      writable: true,
      configurable: true,
      value: { href: '' },
    })
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
    expect(screen.getByText('Done')).toBeTruthy()
  })

  it('shows Step 1 (Create app) content by default', () => {
    render(<EbaySetupPage />)
    expect(screen.getByText('Create your eBay app')).toBeTruthy()
    expect(screen.getByText(/developer.ebay.com/)).toBeTruthy()
  })

  it('advances to Step 2 (credentials) when Next is clicked', () => {
    goToStep2()
    expect(screen.getByLabelText('App Name')).toBeTruthy()
    expect(screen.getByLabelText('App ID (Client ID)')).toBeTruthy()
    expect(screen.getByLabelText('Cert ID (Client Secret)')).toBeTruthy()
    expect(screen.getByLabelText('RuName')).toBeTruthy()
  })

  it('does not show Dev ID field', () => {
    goToStep2()
    expect(screen.queryByLabelText('Dev ID')).toBeNull()
  })

  it('shows environment toggle with Sandbox and Production options', () => {
    goToStep2()
    expect(screen.getByRole('button', { name: /sandbox/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /production/i })).toBeTruthy()
  })

  it('shows validation errors on Step 2 when Next clicked with empty fields', () => {
    goToStep2()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('App name is required')).toBeTruthy()
    expect(screen.getByText('App ID is required')).toBeTruthy()
    expect(screen.getByText('Cert ID is required')).toBeTruthy()
    expect(screen.getByText('RuName is required')).toBeTruthy()
  })

  it('allows navigating back from Step 2', () => {
    goToStep2()
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(screen.getByText('Create your eBay app')).toBeTruthy()
  })

  it('shows RuName as an editable input', () => {
    goToStep2()
    const ruNameInput = screen.getByLabelText('RuName') as HTMLInputElement
    expect(ruNameInput.readOnly).toBe(false)
    fireEvent.change(ruNameInput, { target: { value: 'TestApp-PRD-abc123' } })
    expect(ruNameInput.value).toBe('TestApp-PRD-abc123')
  })

  it('shows automana.app callback URL in RuName hint text', () => {
    goToStep2()
    expect(screen.getByText(/automana\.app/)).toBeTruthy()
  })

  it('shows Cert ID input as password (masked) by default', () => {
    goToStep2()
    const certInput = screen.getByLabelText('Cert ID (Client Secret)') as HTMLInputElement
    expect(certInput.type).toBe('password')
  })

  it('reveals Cert ID when eye button is clicked', () => {
    goToStep2()
    const certInput = screen.getByLabelText('Cert ID (Client Secret)') as HTMLInputElement
    const revealBtn = screen.getByRole('button', { name: /show cert id/i })
    fireEvent.click(revealBtn)
    expect(certInput.type).toBe('text')
  })

  it('advances to Step 3 (scopes) when required credentials are filled', () => {
    goToStep3()
    expect(screen.getByText('Configure OAuth scopes')).toBeTruthy()
  })

  it('renders all OAuth scopes in Step 3', () => {
    goToStep3()
    expect(screen.getByText('sell.inventory')).toBeTruthy()
    expect(screen.getByText('sell.account')).toBeTruthy()
    expect(screen.getByText('sell.marketing')).toBeTruthy()
    expect(screen.getByText('sell.fulfillment')).toBeTruthy()
    expect(screen.getByText('buy.browse')).toBeTruthy()
    expect(screen.getByText('commerce.identity')).toBeTruthy()
  })

  it('shows REQUIRED badges on required scopes', () => {
    goToStep3()
    const badges = screen.getAllByText('REQUIRED')
    expect(badges.length).toBeGreaterThanOrEqual(5)
  })

  it('toggles non-required scope (sell.marketing)', () => {
    goToStep3()
    const marketingToggle = screen.getByRole('switch', { name: /toggle sell\.marketing/i })
    expect(marketingToggle.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(marketingToggle)
    expect(marketingToggle.getAttribute('aria-checked')).toBe('true')
  })

  it('includes toggled scope in registerEbayApp payload after enabling sell.marketing', async () => {
    goToStep3()
    // Enable sell.marketing (off by default)
    const marketingToggle = screen.getByRole('switch', { name: /toggle sell\.marketing/i })
    fireEvent.click(marketingToggle)
    // Submit
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /register app/i }))
    })
    expect(mockRegisterEbayApp).toHaveBeenCalledWith(
      expect.objectContaining({
        allowed_scopes: expect.arrayContaining([
          'https://api.ebay.com/oauth/api_scope/sell.marketing',
        ]),
      })
    )
  })

  it('does not toggle required scopes (sell.inventory stays on)', () => {
    goToStep3()
    const inventoryToggle = screen.getByRole('switch', { name: /toggle sell\.inventory/i })
    expect(inventoryToggle.getAttribute('aria-checked')).toBe('true')
    fireEvent.click(inventoryToggle)
    expect(inventoryToggle.getAttribute('aria-checked')).toBe('true')
  })

  it('calls registerEbayApp with correct payload when Register App clicked', async () => {
    goToStep3()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /register app/i }))
    })
    expect(mockRegisterEbayApp).toHaveBeenCalledWith(
      expect.objectContaining({
        app_name: 'My Store',
        ebay_app_id: 'test-app-id',
        client_secret: 'test-cert-id',
        environment: 'SANDBOX',
        redirect_uri: 'MyApp-MyApp-PRD-ab1234567-89abcdef',
        allowed_scopes: expect.arrayContaining([
          'https://api.ebay.com/oauth/api_scope/sell.inventory',
        ]),
      })
    )
  })

  it('shows success screen on Step 4 after successful registration', async () => {
    goToStep3()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /register app/i }))
    })
    await waitFor(() => {
      expect(screen.getByText('App registered successfully')).toBeTruthy()
      expect(screen.getByText('cool_app_123')).toBeTruthy()
    })
  })

  it('shows inline error on Step 3 when registration fails', async () => {
    mockRegisterEbayApp.mockRejectedValue(new Error('API 400: conflict'))
    goToStep3()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /register app/i }))
    })
    await waitFor(() => {
      expect(screen.getByText('API 400: conflict')).toBeTruthy()
      expect(screen.getByRole('button', { name: /register app/i })).toBeTruthy()
      expect(screen.queryByText('Registration failed')).toBeNull()
    })
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

  describe('Step 4: Connect to eBay', () => {
    it('shows Connect to eBay button on Step 4', async () => {
      await goToStep4()
      expect(screen.getByRole('button', { name: /connect to ebay/i })).toBeInTheDocument()
    })

    it('redirects to eBay authorization URL on connect', async () => {
      await goToStep4()
      await userEvent.click(screen.getByRole('button', { name: /connect to ebay/i }))
      await waitFor(() => {
        expect(mockStartEbayOAuth).toHaveBeenCalledWith('cool_app_123')
        expect(window.location.href).toBe('https://auth.ebay.com/oauth/authorize?test=1')
      })
    })

    it('shows error message when OAuth start fails', async () => {
      mockStartEbayOAuth.mockRejectedValueOnce(new Error('OAuth failed'))
      await goToStep4()
      await userEvent.click(screen.getByRole('button', { name: /connect to ebay/i }))
      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('OAuth failed')
      })
    })
  })
})
