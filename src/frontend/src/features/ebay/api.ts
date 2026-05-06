// src/frontend/src/features/ebay/api.ts
import { apiClient } from '../../lib/apiClient'

export interface RegisterAppRequest {
  app_name: string
  description: string
  environment: 'SANDBOX' | 'PRODUCTION'
  ebay_app_id: string
  client_secret: string
  redirect_uri: string
  allowed_scopes: string[]
}

export interface RegisterAppResponse {
  app_code: string
  message: string
}

export interface StartOAuthResponse {
  authorization_url: string
}

export interface VerifyConnectionResponse {
  expires_in: number
  expires_on: string | null
  scopes: string[]
}

export function getEbayCallbackUrl(): string {
  return `${window.location.origin}/api/integrations/ebay/auth/callback`
}

export async function registerEbayApp(
  payload: RegisterAppRequest
): Promise<RegisterAppResponse> {
  return apiClient<RegisterAppResponse>('/integrations/ebay/auth/admin/apps', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function startEbayOAuth(
  appCode: string
): Promise<StartOAuthResponse> {
  return apiClient<StartOAuthResponse>(
    `/integrations/ebay/auth/app/login?app_code=${encodeURIComponent(appCode)}`,
    { method: 'POST' }
  )
}

export async function verifyEbayConnection(
  appCode: string
): Promise<VerifyConnectionResponse> {
  return apiClient<VerifyConnectionResponse>(
    `/integrations/ebay/auth/exange_token?app_code=${encodeURIComponent(appCode)}`,
    { method: 'POST' }
  )
}
