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
