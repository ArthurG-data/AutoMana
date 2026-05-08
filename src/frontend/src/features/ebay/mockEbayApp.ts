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
