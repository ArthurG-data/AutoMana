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

export interface StartOAuthResponse {
  authorization_url: string
}

export async function startEbayOAuth(appCode: string): Promise<StartOAuthResponse> {
  return apiClient<StartOAuthResponse>(
    `/integrations/ebay/auth/app/login?app_code=${encodeURIComponent(appCode)}`,
    { method: 'POST' }
  )
}
