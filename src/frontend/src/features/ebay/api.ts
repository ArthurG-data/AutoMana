import { apiClient } from '../../lib/apiClient'

export interface EbayScopeItem {
  scope_url: string
  scope_description: string | null
}

export async function fetchEbayScopes(environment: 'SANDBOX' | 'PRODUCTION'): Promise<EbayScopeItem[]> {
  const result = await apiClient<{ scopes: EbayScopeItem[] }>(
    `/integrations/ebay/scopes/?environment=${environment}`
  )
  return result.scopes ?? []
}

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
      // Fixed per backend contract: app_code auto-generated, OAuth2 auth-code flow, premium tier only
      app_code: '',
      response_type: 'code',
      user_requirements: ['premium'],
    }),
  })
}

export interface EbayAppSummary {
  app_id: string
  app_name: string
  app_code: string
  environment: 'SANDBOX' | 'PRODUCTION'
  description: string | null
  is_active: boolean
  is_connected: boolean
  token_expires_at: string | null
  other_user_count: number
  created_at: string
  updated_at: string
}

export interface EbayRateLimit {
  api_name: string
  resource: string
  limit: number
  remaining: number
  reset: string
  time_window_seconds: number
}

export async function fetchUserApps(): Promise<EbayAppSummary[]> {
  const result = await apiClient<{ apps: EbayAppSummary[] }>('/integrations/ebay/auth/apps')
  return result.apps ?? []
}

export async function fetchAppRateLimits(appCode: string): Promise<EbayRateLimit[]> {
  const result = await apiClient<{ rate_limits: EbayRateLimit[] }>(
    `/integrations/ebay/auth/apps/${encodeURIComponent(appCode)}/rate-limits`
  )
  return result.rate_limits ?? []
}

export interface StartOAuthResponse {
  authorization_url: string
}

export async function startEbayOAuth(appCode: string): Promise<StartOAuthResponse> {
  return apiClient<StartOAuthResponse>(
    `/integrations/ebay/auth/app/login?app_code=${encodeURIComponent(appCode)}`,
    { method: 'POST' }
  )
}
