import { apiClient } from '../../lib/apiClient'
import { parseCardTitle, type EbayLiveListing } from './mockListings'

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

// ── Active listings ────────────────────────────────────────────────────────

interface RawEbayItem {
  ItemID?: string | null
  Title?: string | null
  StartPrice?: { currencyID?: string | null; text?: string | number | null } | null
  WatchCount?: number | null
  ConditionDescription?: string | null
  ConditionDisplayName?: string | null
  PictureDetails?: { GalleryURL?: string | string[] } | null
  ListingDetails?: { ViewItemURL?: string | null } | null
  ItemSpecifics?: {
    NameValueList?:
      | Array<{ Name: string; Value: string | string[] }>
      | { Name: string; Value: string | string[] }
  } | null
}

function getFinish(itemSpecifics: RawEbayItem['ItemSpecifics']): 'Foil' | 'Regular' {
  if (!itemSpecifics?.NameValueList) return 'Regular'
  const list = Array.isArray(itemSpecifics.NameValueList)
    ? itemSpecifics.NameValueList
    : [itemSpecifics.NameValueList]
  const finishSpec = list.find((nv) => nv.Name === 'Finish')
  if (!finishSpec) return 'Regular'
  const val = Array.isArray(finishSpec.Value) ? finishSpec.Value[0] : finishSpec.Value
  return val === 'Foil' ? 'Foil' : 'Regular'
}

function getImageUrl(pictureDetails: RawEbayItem['PictureDetails']): string | null {
  if (!pictureDetails?.GalleryURL) return null
  return Array.isArray(pictureDetails.GalleryURL)
    ? (pictureDetails.GalleryURL[0] ?? null)
    : pictureDetails.GalleryURL
}

function mapToLiveListing(raw: RawEbayItem): Omit<EbayLiveListing, 'appCode' | 'appName'> {
  const itemId = raw.ItemID ?? ''
  const { cardName, setInfo } = parseCardTitle(raw.Title ?? '')
  return {
    itemId,
    title: raw.Title ?? '',
    cardName,
    setInfo,
    price: Number(raw.StartPrice?.text ?? 0),
    currency: raw.StartPrice?.currencyID ?? 'AUD',
    conditionLabel: raw.ConditionDisplayName ?? raw.ConditionDescription ?? '',
    finish: getFinish(raw.ItemSpecifics),
    watchCount: raw.WatchCount ?? 0,
    viewItemUrl:
      raw.ListingDetails?.ViewItemURL ?? `https://www.ebay.com.au/itm/${itemId}`,
    imageUrl: getImageUrl(raw.PictureDetails),
  }
}

export async function fetchActiveListings(
  appCode: string,
  limit = 50,
  offset = 0,
): Promise<EbayLiveListing[]> {
  // PaginatedResponse returns { data: [...], pagination: {...} }, not a bare array.
  // Be defensive: handle both shapes so unit tests (which mock a bare array) and
  // the real backend (which wraps in .data) both work.
  const raw = await apiClient<unknown>(
    `/listing/active?app_code=${encodeURIComponent(appCode)}&limit=${limit}&offset=${offset}`
  )
  const items: RawEbayItem[] = Array.isArray(raw)
    ? raw
    : Array.isArray((raw as { data?: unknown }).data)
      ? (raw as { data: RawEbayItem[] }).data
      : []
  return items.map((item) => ({ ...mapToLiveListing(item), appCode, appName: '' }))
}
