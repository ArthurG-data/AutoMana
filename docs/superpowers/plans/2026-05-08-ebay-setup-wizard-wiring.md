# eBay Setup Wizard Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `/ebay/setup` 4-step wizard to `POST /api/integrations/ebay/auth/admin/apps`, replacing all mock data with real API calls and adding the missing form fields the backend requires.

**Architecture:** Three frontend layers change: (1) `mockEbayApp.ts` gains full eBay scope URLs and a `RegistrationResult` type; (2) a new `features/ebay/api.ts` owns the `registerEbayApp()` call; (3) `setup.tsx` wires the wizard — adds `app_name`, `description`, and environment fields to Step 2, calls the API on Step 3 "Next", and replaces the fake verify step with a registration result screen. No backend changes needed.

**Tech Stack:** React 18, TypeScript, TanStack Router, Vitest + Testing Library, existing `apiClient` wrapper, CSS Modules.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/frontend/src/features/ebay/mockEbayApp.ts` | Modify | Add `scopeUrl` to `OAuthScope`, full eBay scope URLs, `RegistrationResult` type; remove `devId` from `EbayCredentials` |
| `src/frontend/src/features/ebay/api.ts` | **Create** | `registerEbayApp()` — single POST to backend |
| `src/frontend/src/routes/ebay/Setup.module.css` | Modify | Add `.envToggle`, `.envOption`, `.envOptionActive` for environment segmented control |
| `src/frontend/src/routes/ebay/setup.tsx` | Modify | New fields on Step 2, async submit on Step 3, result screen on Step 4 |
| `src/frontend/src/routes/ebay/__tests__/setup.test.tsx` | Modify | Remove Dev ID assertions, add new field assertions, mock API, test submit flow |

---

## Task 1: Update mockEbayApp.ts types and scope URLs

**Files:**
- Modify: `src/frontend/src/features/ebay/mockEbayApp.ts`

- [ ] **Step 1: Update `mockEbayApp.ts`**

Replace the entire file with:

```typescript
// src/frontend/src/features/ebay/mockEbayApp.ts

// ── Types ─────────────────────────────────────────────────────────────────

export interface EbayCredentials {
  appId: string       // Client ID (ebay_app_id)
  certId: string      // Client Secret
  ruName: string      // Redirect URI — read-only, provided by backend config
}

export interface OAuthScope {
  id: string
  name: string
  description: string
  scopeUrl: string    // Full eBay scope URL sent to the backend
  required: boolean
  enabled: boolean
}

export type RegistrationResult =
  | { success: true; appCode: string }
  | { success: false; error: string }

export interface ConnectionStatus {
  connected: boolean
  environment: 'sandbox' | 'production'
  lastVerified: string | null
  tokenExpires: string | null
  dailyQuota: number
  usedToday: number
}

export type SetupStep = 0 | 1 | 2 | 3

// ── Constants ──────────────────────────────────────────────────────────────

export const REDIRECT_URI = 'https://auth.automana.app/oauth/callback/ebay'

export const MOCK_OAUTH_SCOPES: OAuthScope[] = [
  {
    id: 'sell.inventory',
    name: 'sell.inventory',
    description: 'Read and manage your eBay inventory listings',
    scopeUrl: 'https://api.ebay.com/oauth/api_scope/sell.inventory',
    required: true,
    enabled: true,
  },
  {
    id: 'sell.account',
    name: 'sell.account',
    description: 'Access your eBay seller account settings',
    scopeUrl: 'https://api.ebay.com/oauth/api_scope/sell.account',
    required: true,
    enabled: true,
  },
  {
    id: 'sell.marketing',
    name: 'sell.marketing',
    description: 'Create and manage eBay marketing promotions',
    scopeUrl: 'https://api.ebay.com/oauth/api_scope/sell.marketing',
    required: false,
    enabled: false,
  },
  {
    id: 'sell.fulfillment',
    name: 'sell.fulfillment',
    description: 'Manage order fulfillment and shipping details',
    scopeUrl: 'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
    required: true,
    enabled: true,
  },
  {
    id: 'buy.browse',
    name: 'buy.browse',
    description: 'Search and browse eBay item catalog for pricing',
    scopeUrl: 'https://api.ebay.com/oauth/api_scope/buy.browse',
    required: true,
    enabled: true,
  },
  {
    id: 'commerce.identity',
    name: 'commerce.identity',
    description: 'Access verified identity for user authorization',
    scopeUrl: 'https://api.ebay.com/oauth/api_scope/commerce.identity.readonly',
    required: true,
    enabled: true,
  },
]

export const MOCK_CONNECTION_STATUS: ConnectionStatus = {
  connected: false,
  environment: 'production',
  lastVerified: null,
  tokenExpires: null,
  dailyQuota: 5000,
  usedToday: 0,
}

export const MOCK_CONNECTED_STATUS: ConnectionStatus = {
  connected: true,
  environment: 'production',
  lastVerified: '2026-05-06T10:32:00Z',
  tokenExpires: '2026-06-06T10:32:00Z',
  dailyQuota: 5000,
  usedToday: 247,
}

export const SETUP_STEPS = [
  { label: 'Create app' },
  { label: 'Paste keys' },
  { label: 'OAuth scopes' },
  { label: 'Done' },
]

// ── Help links ─────────────────────────────────────────────────────────────

export const HELP_LINKS = [
  { label: 'eBay Developer Portal', href: 'https://developer.ebay.com' },
  { label: 'Create an application', href: 'https://developer.ebay.com/my/keys' },
  { label: 'Configure RuName', href: 'https://developer.ebay.com/my/auth' },
  { label: 'OAuth scope reference', href: 'https://developer.ebay.com/api-docs/static/oauth-scopes.html' },
]

export const BYOA_BENEFITS = [
  'Your API quota is never shared with other AutoMana users',
  'Credentials stay in your eBay account — we only store tokens',
  'Revoke access instantly from the eBay developer portal',
  'Sandbox support for testing without live listings',
]
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/features/ebay/mockEbayApp.ts
git commit -m "feat(ebay): add scopeUrl to OAuthScope and RegistrationResult type"
```

---

## Task 2: Create features/ebay/api.ts

**Files:**
- Create: `src/frontend/src/features/ebay/api.ts`

- [ ] **Step 1: Write a failing test for `registerEbayApp`**

Create `src/frontend/src/features/ebay/__tests__/api.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { registerEbayApp } from '../api'

// Mock apiClient at the module level
vi.mock('../../../lib/apiClient', () => ({
  apiClient: vi.fn(),
}))

import { apiClient } from '../../../lib/apiClient'

const mockApiClient = vi.mocked(apiClient)

describe('registerEbayApp', () => {
  beforeEach(() => {
    mockApiClient.mockReset()
  })

  it('calls POST /integrations/ebay/auth/admin/apps with correct body', async () => {
    mockApiClient.mockResolvedValue({ message: 'eBay app registered successfully', app_code: 'cool_app_123' })

    const result = await registerEbayApp({
      app_name: 'My Store',
      description: 'Test app',
      environment: 'SANDBOX',
      ebay_app_id: 'MyApp-1234',
      client_secret: 'SBX-secret',
      redirect_uri: 'https://auth.automana.app/oauth/callback/ebay',
      allowed_scopes: ['https://api.ebay.com/oauth/api_scope/sell.inventory'],
    })

    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/auth/admin/apps',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"app_name":"My Store"'),
      })
    )
    expect(result.app_code).toBe('cool_app_123')
  })

  it('defaults app_code to empty string', async () => {
    mockApiClient.mockResolvedValue({ message: 'ok', app_code: 'auto_123' })

    await registerEbayApp({
      app_name: 'X',
      description: '',
      environment: 'PRODUCTION',
      ebay_app_id: 'id',
      client_secret: 'secret',
      redirect_uri: 'https://example.com',
      allowed_scopes: [],
    })

    const body = JSON.parse((mockApiClient.mock.calls[0][1] as RequestInit).body as string)
    expect(body.app_code).toBe('')
  })

  it('propagates errors from apiClient', async () => {
    mockApiClient.mockRejectedValue(new Error('API 403: forbidden'))
    await expect(
      registerEbayApp({
        app_name: 'X',
        description: '',
        environment: 'SANDBOX',
        ebay_app_id: 'id',
        client_secret: 'secret',
        redirect_uri: 'https://example.com',
        allowed_scopes: [],
      })
    ).rejects.toThrow('API 403: forbidden')
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/ebay/__tests__/api.test.ts
```

Expected: FAIL with "Cannot find module '../api'"

- [ ] **Step 3: Create `features/ebay/api.ts`**

```typescript
// src/frontend/src/features/ebay/api.ts
import { apiClient } from '../../lib/apiClient'

export interface RegisterEbayAppRequest {
  app_name: string
  description: string
  environment: 'SANDBOX' | 'PRODUCTION'
  ebay_app_id: string
  client_secret: string
  redirect_uri: string
  allowed_scopes: string[]
}

export interface RegisterEbayAppResponse {
  message: string
  app_code: string
}

export async function registerEbayApp(data: RegisterEbayAppRequest): Promise<RegisterEbayAppResponse> {
  return apiClient<RegisterEbayAppResponse>('/integrations/ebay/auth/admin/apps', {
    method: 'POST',
    body: JSON.stringify({
      app_name: data.app_name,
      description: data.description,
      environment: data.environment,
      ebay_app_id: data.ebay_app_id,
      client_secret: data.client_secret,
      redirect_uri: data.redirect_uri,
      allowed_scopes: data.allowed_scopes,
      app_code: '',
      response_type: 'code',
      user_requirements: ['premium'],
    }),
  })
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd src/frontend && npx vitest run src/frontend/src/features/ebay/__tests__/api.test.ts
```

Expected: 3 passing

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/api.ts src/frontend/src/features/ebay/__tests__/api.test.ts
git commit -m "feat(ebay): add registerEbayApp API function"
```

---

## Task 3: Add new fields to Step 2 (credentials)

**Files:**
- Modify: `src/frontend/src/routes/ebay/Setup.module.css`
- Modify: `src/frontend/src/routes/ebay/setup.tsx`
- Modify: `src/frontend/src/routes/ebay/__tests__/setup.test.tsx`

- [ ] **Step 1: Add CSS for environment segmented control**

Append to the end of `src/frontend/src/routes/ebay/Setup.module.css`:

```css
/* ── Environment segmented control ───────────────────────── */
.envToggle {
  display: flex;
  border: 1px solid var(--hd-border);
  border-radius: 6px;
  overflow: hidden;
  width: fit-content;
}

.envOption {
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: transparent;
  border: none;
  color: var(--hd-sub);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.envOption + .envOption {
  border-left: 1px solid var(--hd-border);
}

.envOptionActive {
  background: var(--hd-accent);
  color: var(--hd-bg);
}
```

- [ ] **Step 2: Update the failing tests first**

Replace the full content of `src/frontend/src/routes/ebay/__tests__/setup.test.tsx` with:

```typescript
// src/frontend/src/routes/ebay/__tests__/setup.test.tsx
import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
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
}))

import { registerEbayApp } from '../../../features/ebay/api'
const mockRegisterEbayApp = vi.mocked(registerEbayApp)

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
  fireEvent.click(screen.getByRole('button', { name: /next/i }))
}

describe('EbaySetupPage', () => {
  beforeEach(() => {
    writeTextMock.mockClear()
    mockRegisterEbayApp.mockReset()
    mockRegisterEbayApp.mockResolvedValue({
      message: 'eBay app registered successfully',
      app_code: 'cool_app_123',
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
  })

  it('allows navigating back from Step 2', () => {
    goToStep2()
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(screen.getByText('Create your eBay app')).toBeTruthy()
  })

  it('copies Redirect URI to clipboard when copy button clicked', async () => {
    goToStep2()
    const copyBtn = screen.getByRole('button', { name: /copy redirect uri/i })
    fireEvent.click(copyBtn)
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining('automana.app'))
    })
  })

  it('shows Redirect URI as read-only input', () => {
    goToStep2()
    const ruNameInput = screen.getByLabelText(/redirect uri/i) as HTMLInputElement
    expect(ruNameInput.readOnly).toBe(true)
    expect(ruNameInput.value).toContain('automana.app')
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
        redirect_uri: expect.stringContaining('automana.app'),
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

  it('shows error screen on Step 4 when registration fails', async () => {
    mockRegisterEbayApp.mockRejectedValue(new Error('API 400: conflict'))
    goToStep3()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /register app/i }))
    })
    await waitFor(() => {
      expect(screen.getByText('Registration failed')).toBeTruthy()
      expect(screen.getByText('API 400: conflict')).toBeTruthy()
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
})
```

- [ ] **Step 3: Run updated tests — expect FAIL**

```bash
cd src/frontend && npx vitest run src/frontend/src/routes/ebay/__tests__/setup.test.tsx
```

Expected: multiple failures (new labels not rendered yet, registerEbayApp not wired, Step 4 content different)

- [ ] **Step 4: Update `setup.tsx` — replace full file**

```typescript
// src/frontend/src/routes/ebay/setup.tsx
import React, { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { AppShell } from '../../components/layout/AppShell'
import { TopBar } from '../../components/layout/TopBar'
import { Button } from '../../components/ui/Button'
import { Toggle } from '../../components/ui/Toggle'
import { Icon } from '../../components/design-system/Icon'
import {
  MOCK_OAUTH_SCOPES,
  REDIRECT_URI,
  SETUP_STEPS,
  HELP_LINKS,
  BYOA_BENEFITS,
  MOCK_CONNECTION_STATUS,
  type OAuthScope,
  type ConnectionStatus,
  type RegistrationResult,
} from '../../features/ebay/mockEbayApp'
import { registerEbayApp } from '../../features/ebay/api'
import styles from './Setup.module.css'

export const Route = createFileRoute('/ebay/setup')({
  component: EbaySetupPage,
})

export { EbaySetupPage }

// ── Step 1: Create app instructions ───────────────────────────────────────

function StepCreateApp() {
  return (
    <div className={styles.stepContent}>
      <h2 className={styles.stepHeading}>Create your eBay app</h2>
      <p className={styles.stepDesc}>
        You'll need a free eBay developer account to generate API credentials for AutoMana.
      </p>
      <ol className={styles.instructionList}>
        <li>
          Go to{' '}
          <a
            href="https://developer.ebay.com"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.externalLink}
          >
            developer.ebay.com
          </a>{' '}
          and sign in (or create a free account).
        </li>
        <li>
          Navigate to <strong>Application Keys</strong> in the top navigation.
        </li>
        <li>
          Click <strong>Create a keyset</strong>, choose <em>Production</em>, and name your app
          (e.g., "AutoMana").
        </li>
        <li>
          Copy the <strong>App ID (Client ID)</strong> and <strong>Cert ID</strong> — you'll
          paste them in the next step.
        </li>
      </ol>
      <div className={styles.infoBox}>
        <Icon kind="shield" size={14} color="var(--hd-blue)" />
        <span>
          eBay developer accounts are free. Your credentials are encrypted at rest and never
          shared with other AutoMana users.
        </span>
      </div>
    </div>
  )
}

// ── Step 2: Paste credentials ──────────────────────────────────────────────

type Environment = 'SANDBOX' | 'PRODUCTION'

interface StepCredentialsProps {
  appName: string
  description: string
  environment: Environment
  appId: string
  certId: string
  onAppNameChange: (v: string) => void
  onDescriptionChange: (v: string) => void
  onEnvironmentChange: (v: Environment) => void
  onAppIdChange: (v: string) => void
  onCertIdChange: (v: string) => void
  errors: Record<string, string>
}

function StepCredentials({
  appName,
  description,
  environment,
  appId,
  certId,
  onAppNameChange,
  onDescriptionChange,
  onEnvironmentChange,
  onAppIdChange,
  onCertIdChange,
  errors,
}: StepCredentialsProps) {
  const [certRevealed, setCertRevealed] = useState(false)
  const [copied, setCopied] = useState(false)

  function copyRuName() {
    navigator.clipboard.writeText(REDIRECT_URI).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className={styles.stepContent}>
      <h2 className={styles.stepHeading}>Paste your eBay credentials</h2>
      <p className={styles.stepDesc}>
        Find these in the eBay Developer Portal under <strong>Application Keys</strong>.
      </p>

      <div className={styles.formGrid}>
        {/* App Name */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-app-name">
            App Name
          </label>
          <div className={styles.inputWrapper}>
            <Icon kind="tag" size={14} color="var(--hd-muted)" />
            <input
              id="ebay-app-name"
              className={[styles.input, errors.appName ? styles.inputError : ''].filter(Boolean).join(' ')}
              type="text"
              placeholder="My AutoMana Store"
              value={appName}
              onChange={(e) => onAppNameChange(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          {errors.appName && <span className={styles.errorMsg}>{errors.appName}</span>}
        </div>

        {/* Description */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-description">
            Description
            <span className={styles.readOnlyTag}>optional</span>
          </label>
          <div className={styles.inputWrapper}>
            <input
              id="ebay-description"
              className={styles.input}
              type="text"
              placeholder="e.g. My main eBay seller account"
              value={description}
              onChange={(e) => onDescriptionChange(e.target.value)}
              autoComplete="off"
            />
          </div>
        </div>

        {/* Environment */}
        <div className={styles.field}>
          <label className={styles.fieldLabel}>
            Environment
          </label>
          <div className={styles.envToggle}>
            <button
              type="button"
              className={[styles.envOption, environment === 'SANDBOX' ? styles.envOptionActive : ''].filter(Boolean).join(' ')}
              onClick={() => onEnvironmentChange('SANDBOX')}
              aria-pressed={environment === 'SANDBOX'}
            >
              Sandbox
            </button>
            <button
              type="button"
              className={[styles.envOption, environment === 'PRODUCTION' ? styles.envOptionActive : ''].filter(Boolean).join(' ')}
              onClick={() => onEnvironmentChange('PRODUCTION')}
              aria-pressed={environment === 'PRODUCTION'}
            >
              Production
            </button>
          </div>
        </div>

        {/* App ID */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-app-id">
            App ID (Client ID)
          </label>
          <div className={styles.inputWrapper}>
            <Icon kind="key" size={14} color="var(--hd-muted)" />
            <input
              id="ebay-app-id"
              className={[styles.input, errors.appId ? styles.inputError : ''].filter(Boolean).join(' ')}
              type="text"
              placeholder="YourApp-1234-5678-ABCD-efg12345"
              value={appId}
              onChange={(e) => onAppIdChange(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          {errors.appId && <span className={styles.errorMsg}>{errors.appId}</span>}
        </div>

        {/* Cert ID */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-cert-id">
            Cert ID (Client Secret)
          </label>
          <div className={styles.inputWrapper}>
            <Icon kind="shield" size={14} color="var(--hd-muted)" />
            <input
              id="ebay-cert-id"
              className={[styles.input, errors.certId ? styles.inputError : ''].filter(Boolean).join(' ')}
              type={certRevealed ? 'text' : 'password'}
              placeholder="SBX-1234abcd-efgh-5678"
              value={certId}
              onChange={(e) => onCertIdChange(e.target.value)}
              autoComplete="new-password"
              spellCheck={false}
            />
            <button
              type="button"
              className={styles.revealBtn}
              onClick={() => setCertRevealed((v) => !v)}
              aria-label={certRevealed ? 'Hide Cert ID' : 'Show Cert ID'}
            >
              <Icon kind="eye" size={13} color="var(--hd-muted)" />
            </button>
          </div>
          {errors.certId && <span className={styles.errorMsg}>{errors.certId}</span>}
        </div>

        {/* Redirect URI (read-only) */}
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="ebay-runame">
            Redirect URI (RuName)
            <span className={styles.readOnlyTag}>read-only</span>
          </label>
          <div className={styles.inputWrapper}>
            <Icon kind="link" size={14} color="var(--hd-muted)" />
            <input
              id="ebay-runame"
              className={[styles.input, styles.inputReadOnly].join(' ')}
              type="text"
              value={REDIRECT_URI}
              readOnly
              aria-readonly="true"
            />
            <button
              type="button"
              className={styles.copyBtn}
              onClick={copyRuName}
              aria-label="Copy Redirect URI"
            >
              {copied ? (
                <Icon kind="check" size={13} color="var(--hd-accent)" />
              ) : (
                <Icon kind="copy" size={13} color="var(--hd-muted)" />
              )}
            </button>
          </div>
          <p className={styles.fieldHint}>
            Paste this URL into your eBay app's <strong>Auth accepted URL</strong> field in the
            developer portal, then add it as an allowed RuName.
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Step 3: OAuth scopes ───────────────────────────────────────────────────

interface StepScopesProps {
  scopes: OAuthScope[]
  onToggle: (id: string) => void
}

function StepScopes({ scopes, onToggle }: StepScopesProps) {
  return (
    <div className={styles.stepContent}>
      <h2 className={styles.stepHeading}>Configure OAuth scopes</h2>
      <p className={styles.stepDesc}>
        These permissions determine what AutoMana can do on your eBay account. Required scopes
        cannot be disabled.
      </p>

      <div className={styles.scopeList} role="list">
        {scopes.map((scope) => (
          <div key={scope.id} className={styles.scopeRow} role="listitem">
            <div className={styles.scopeInfo}>
              <div className={styles.scopeNameRow}>
                <span className={styles.scopeName}>{scope.name}</span>
                {scope.required && (
                  <span className={styles.requiredBadge}>REQUIRED</span>
                )}
              </div>
              <span className={styles.scopeDesc}>{scope.description}</span>
            </div>
            <Toggle
              on={scope.enabled}
              onToggle={scope.required ? undefined : () => onToggle(scope.id)}
              label={`Toggle ${scope.name}`}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Step 4: Registration result ────────────────────────────────────────────

interface StepResultProps {
  result: RegistrationResult
}

function StepResult({ result }: StepResultProps) {
  if (result.success) {
    return (
      <div className={styles.stepContent}>
        <h2 className={styles.stepHeading}>App registered</h2>
        <div className={styles.verifyBox}>
          <div className={styles.verifySuccess}>
            <div className={styles.verifyIcon}>
              <Icon kind="check" size={24} color="var(--hd-accent)" />
            </div>
            <div>
              <div className={styles.verifyTitle}>App registered successfully</div>
              <div className={styles.verifySubtitle}>
                App code: <code>{result.appCode}</code>
              </div>
            </div>
          </div>
        </div>
        <p className={styles.verifyNote}>
          Your eBay app is registered. Use the app code above to start the OAuth flow and
          connect your eBay account.
        </p>
      </div>
    )
  }
  return (
    <div className={styles.stepContent}>
      <h2 className={styles.stepHeading}>Registration failed</h2>
      <div className={styles.verifyBox}>
        <div className={styles.verifyIdle}>
          <div className={styles.verifyIcon}>
            <Icon kind="shield" size={24} color="var(--hd-red)" />
          </div>
          <div>
            <div className={styles.verifyTitle}>Could not register app</div>
            <div className={styles.verifySubtitle}>{result.error}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Stepper indicator ──────────────────────────────────────────────────────

interface StepperProps {
  steps: { label: string }[]
  current: number
  completed: Set<number>
}

function Stepper({ steps, current, completed }: StepperProps) {
  return (
    <div className={styles.stepper} role="list" aria-label="Setup steps">
      {steps.map((step, i) => {
        const isDone = completed.has(i)
        const isActive = i === current
        return (
          <div
            key={i}
            className={[
              styles.stepItem,
              isActive ? styles.stepItemActive : '',
              isDone ? styles.stepItemDone : '',
            ].filter(Boolean).join(' ')}
            role="listitem"
          >
            <div className={styles.stepNumber} aria-hidden="true">
              {isDone ? <Icon kind="check" size={11} color="var(--hd-bg)" /> : i + 1}
            </div>
            <span className={styles.stepLabel}>{step.label}</span>
            {i < steps.length - 1 && <div className={styles.stepConnector} aria-hidden="true" />}
          </div>
        )
      })}
    </div>
  )
}

// ── Connection status sidebar panel ───────────────────────────────────────

interface StatusPanelProps {
  status: ConnectionStatus
}

function StatusPanel({ status }: StatusPanelProps) {
  const quotaPct = status.dailyQuota > 0
    ? Math.round((status.usedToday / status.dailyQuota) * 100)
    : 0

  return (
    <div className={styles.sidePanel}>
      <div className={styles.sidePanelTitle}>Connection status</div>
      <div className={styles.statusDot}>
        <span
          className={styles.statusIndicator}
          style={{ background: status.connected ? 'var(--hd-accent)' : 'var(--hd-sub)' }}
          aria-hidden="true"
        />
        <span className={styles.statusLabel}>
          {status.connected ? 'Connected' : 'Not connected'}
        </span>
      </div>

      <div className={styles.metricList}>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Environment</span>
          <span className={styles.metricVal}>{status.environment}</span>
        </div>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Last verified</span>
          <span className={styles.metricVal}>
            {status.lastVerified
              ? new Date(status.lastVerified).toLocaleDateString()
              : '—'}
          </span>
        </div>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Token expires</span>
          <span className={styles.metricVal}>
            {status.tokenExpires
              ? new Date(status.tokenExpires).toLocaleDateString()
              : '—'}
          </span>
        </div>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Daily quota</span>
          <span className={styles.metricVal}>{status.dailyQuota.toLocaleString()}</span>
        </div>
        <div className={styles.metricRow}>
          <span className={styles.metricKey}>Used today</span>
          <span className={styles.metricVal}>{status.usedToday}</span>
        </div>
      </div>

      {status.connected && (
        <div className={styles.quotaBarWrapper}>
          <div
            className={styles.quotaBar}
            role="progressbar"
            aria-valuenow={status.usedToday}
            aria-valuemax={status.dailyQuota}
            aria-label="Daily quota usage"
          >
            <div
              className={styles.quotaFill}
              style={{
                width: `${quotaPct}%`,
                background: quotaPct > 80 ? 'var(--hd-red)' : 'var(--hd-accent)',
              }}
            />
          </div>
          <span className={styles.quotaPct}>{quotaPct}%</span>
        </div>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

function EbaySetupPage() {
  const [step, setStep] = useState<number>(0)
  const [completed, setCompleted] = useState<Set<number>>(new Set())

  // Step 2 form state
  const [appName, setAppName] = useState('')
  const [description, setDescription] = useState('')
  const [environment, setEnvironment] = useState<Environment>('SANDBOX')
  const [appId, setAppId] = useState('')
  const [certId, setCertId] = useState('')
  const [formErrors, setFormErrors] = useState<Record<string, string>>({})

  // Step 3 state
  const [scopes, setScopes] = useState(MOCK_OAUTH_SCOPES)

  // Step 4 state
  const [submitting, setSubmitting] = useState(false)
  const [registrationResult, setRegistrationResult] = useState<RegistrationResult | null>(null)

  function validateCredentials(): boolean {
    const errors: Record<string, string> = {}
    if (!appName.trim()) errors.appName = 'App name is required'
    if (!appId.trim()) errors.appId = 'App ID is required'
    if (!certId.trim()) errors.certId = 'Cert ID is required'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  function toggleScope(id: string) {
    setScopes((prev) =>
      prev.map((s) => (s.id === id && !s.required ? { ...s, enabled: !s.enabled } : s))
    )
  }

  async function handleNext() {
    if (step === 1 && !validateCredentials()) return

    if (step === 2) {
      setSubmitting(true)
      try {
        const enabledScopeUrls = scopes.filter((s) => s.enabled).map((s) => s.scopeUrl)
        const result = await registerEbayApp({
          app_name: appName,
          description,
          environment,
          ebay_app_id: appId,
          client_secret: certId,
          redirect_uri: REDIRECT_URI,
          allowed_scopes: enabledScopeUrls,
        })
        setRegistrationResult({ success: true, appCode: result.app_code })
      } catch (err) {
        setRegistrationResult({
          success: false,
          error: err instanceof Error ? err.message : 'Registration failed',
        })
      } finally {
        setSubmitting(false)
        setCompleted((prev) => new Set(prev).add(step))
        setStep((s) => s + 1)
      }
      return
    }

    setCompleted((prev) => new Set(prev).add(step))
    setStep((s) => Math.min(s + 1, SETUP_STEPS.length - 1))
  }

  function handleBack() {
    setStep((s) => Math.max(s - 1, 0))
  }

  return (
    <AppShell active="settings">
      <TopBar
        title="Connect your eBay app"
        subtitle="eBay Developer"
        breadcrumb="Settings / Integrations"
      />

      <div className={styles.page}>
        <Stepper steps={SETUP_STEPS} current={step} completed={completed} />

        <div className={styles.contentGrid}>
          <div className={styles.mainPanel}>
            {step === 0 && <StepCreateApp />}
            {step === 1 && (
              <StepCredentials
                appName={appName}
                description={description}
                environment={environment}
                appId={appId}
                certId={certId}
                onAppNameChange={(v) => { setAppName(v); setFormErrors((e) => ({ ...e, appName: '' })) }}
                onDescriptionChange={setDescription}
                onEnvironmentChange={setEnvironment}
                onAppIdChange={(v) => { setAppId(v); setFormErrors((e) => ({ ...e, appId: '' })) }}
                onCertIdChange={(v) => { setCertId(v); setFormErrors((e) => ({ ...e, certId: '' })) }}
                errors={formErrors}
              />
            )}
            {step === 2 && <StepScopes scopes={scopes} onToggle={toggleScope} />}
            {step === 3 && registrationResult && <StepResult result={registrationResult} />}

            <div className={styles.navButtons}>
              {step > 0 && step < SETUP_STEPS.length - 1 && (
                <Button variant="ghost" size="md" onClick={handleBack}>
                  Back
                </Button>
              )}
              {step < SETUP_STEPS.length - 1 && (
                <Button
                  variant="accent"
                  size="md"
                  onClick={handleNext}
                  disabled={submitting}
                  icon={step === 2 ? undefined : <Icon kind="arrowRight" size={13} color="currentColor" />}
                >
                  {step === 2
                    ? submitting ? 'Registering…' : 'Register App'
                    : 'Next'}
                </Button>
              )}
            </div>
          </div>

          <aside className={styles.sidebar} aria-label="eBay setup sidebar">
            <StatusPanel status={MOCK_CONNECTION_STATUS} />

            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Why bring your own app?</div>
              <ul className={styles.benefitList}>
                {BYOA_BENEFITS.map((benefit) => (
                  <li key={benefit} className={styles.benefitItem}>
                    <Icon kind="check" size={12} color="var(--hd-accent)" />
                    <span>{benefit}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Need help?</div>
              <div className={styles.helpLinks}>
                {HELP_LINKS.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.helpLink}
                  >
                    <Icon kind="link" size={11} color="var(--hd-muted)" />
                    {link.label}
                  </a>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd src/frontend && npx vitest run src/frontend/src/routes/ebay/__tests__/setup.test.tsx
```

Expected: all tests passing. If `Icon kind="tag"` doesn't exist in the Icon component, replace with `kind="key"` as a fallback (check `src/frontend/src/components/design-system/Icon.tsx` for available kinds).

- [ ] **Step 6: Commit**

```bash
git add \
  src/frontend/src/routes/ebay/Setup.module.css \
  src/frontend/src/routes/ebay/setup.tsx \
  src/frontend/src/routes/ebay/__tests__/setup.test.tsx
git commit -m "feat(ebay): wire setup wizard to POST /admin/apps with new credential fields"
```

---

## Self-Review

**Spec coverage:**
- ✅ Wire to `POST /api/integrations/ebay/auth/admin/apps` — Task 2 + 3
- ✅ Add `app_name`, `description`, environment toggle to Step 2 — Task 3
- ✅ Remove Dev ID — Task 3
- ✅ Submission triggered by "Next" on Step 3 (scopes) — Task 3
- ✅ Step 4 shows success with `app_code` or error with message — Task 3
- ✅ `app_code` sent as `""` for backend auto-generation — Task 2
- ✅ `redirect_uri` hardcoded as constant — Task 1

**Placeholder scan:** None found. All code is complete.

**Type consistency:**
- `OAuthScope.scopeUrl` defined in Task 1, used in Task 3 (`s.scopeUrl`)
- `RegistrationResult` defined in Task 1, used as `StepResultProps.result` in Task 3
- `RegisterEbayAppRequest` / `RegisterEbayAppResponse` defined in Task 2, consumed in Task 3
- `REDIRECT_URI` (renamed from `MOCK_REDIRECT_URI`) defined in Task 1, used in Task 3 and tests
- `Environment` type defined locally in `setup.tsx` — consistent with backend enum values `'SANDBOX' | 'PRODUCTION'`
