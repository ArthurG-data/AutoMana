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

// FastAPI serializes ItemModel using Pydantic aliases (camelCase).
// PictureDetails and ItemSpecifics are raw dicts — their inner eBay XML keys (GalleryURL, NameValueList) are preserved as-is.
interface RawEbayItem {
  itemID?: string | null
  title?: string | null
  // Fixed-price listings return BuyItNowPrice; auction listings return StartPrice.
  buyItNowPrice?: { currency?: string | null; value?: string | number | null } | null
  startPrice?: { currency?: string | null; value?: string | number | null } | null
  sellingStatus?: { currentPrice?: { currency?: string | null; value?: string | number | null } | null } | null
  watchCount?: number | null
  conditionID?: number | null
  conditionDescription?: string | null
  conditionDisplayName?: string | null
  pictureDetails?: { GalleryURL?: string | string[] } | null
  listingDetails?: { viewItemUrl?: string | null; startTime?: string | null } | null
  itemSpecifics?: {
    NameValueList?:
      | Array<{ Name: string; Value: string | string[] }>
      | { Name: string; Value: string | string[] }
  } | null
}

// Generic eBay condition ID → label fallback for when ConditionDisplayName is absent.
function ebayConditionLabel(id?: number | null): string {
  switch (id) {
    case 1000: return 'New'
    case 1500: return 'New other'
    case 2000: return 'Refurbished'
    case 2500: return 'Seller refurb'
    case 3000: return 'Used'
    case 4000: return 'Very Good'
    case 5000: return 'Good'
    case 6000: return 'Acceptable'
    case 7000: return 'For parts'
    default: return ''
  }
}

function getSpecificValue(
  itemSpecifics: RawEbayItem['itemSpecifics'],
  name: string,
): string | null {
  if (!itemSpecifics?.NameValueList) return null
  const list = Array.isArray(itemSpecifics.NameValueList)
    ? itemSpecifics.NameValueList
    : [itemSpecifics.NameValueList]
  const entry = list.find((nv) => nv.Name === name)
  if (!entry) return null
  const val = Array.isArray(entry.Value) ? entry.Value[0] : entry.Value
  return val ?? null
}

function getFinish(itemSpecifics: RawEbayItem['itemSpecifics']): string {
  const val = getSpecificValue(itemSpecifics, 'Finish')
  if (!val) return ''
  if (val.toLowerCase() === 'non-foil') return 'Regular'
  return val
}

function calcDaysListed(startTime?: string | null): number {
  if (!startTime) return 0
  const ms = Date.now() - new Date(startTime).getTime()
  return Math.max(0, Math.floor(ms / 86_400_000))
}

function getStyle(itemSpecifics: RawEbayItem['itemSpecifics']): string {
  return (
    getSpecificValue(itemSpecifics, 'Card Style') ??
    getSpecificValue(itemSpecifics, 'Frame Type') ??
    getSpecificValue(itemSpecifics, 'Treatment') ??
    getSpecificValue(itemSpecifics, 'Card Treatment') ??
    getSpecificValue(itemSpecifics, 'Variant') ??
    ''
  )
}

function getImageUrl(pictureDetails: RawEbayItem['pictureDetails']): string | null {
  if (!pictureDetails?.GalleryURL) return null
  return Array.isArray(pictureDetails.GalleryURL)
    ? (pictureDetails.GalleryURL[0] ?? null)
    : pictureDetails.GalleryURL
}

function mapToLiveListing(raw: RawEbayItem): Omit<EbayLiveListing, 'appCode' | 'appName'> {
  const itemId = raw.itemID ?? ''
  const { cardName, setCode, setInfo, titleFinish, titleStyle } = parseCardTitle(raw.title ?? '')
  const priceObj =
    raw.buyItNowPrice ??
    raw.sellingStatus?.currentPrice ??
    raw.startPrice ??
    null
  return {
    itemId,
    title: raw.title ?? '',
    cardName,
    setCode,
    setInfo,
    price: Number(priceObj?.value ?? 0),
    currency: priceObj?.currency ?? 'AUD',
    conditionLabel:
      raw.conditionDisplayName ??
      raw.conditionDescription ??
      ebayConditionLabel(raw.conditionID),
    // ItemSpecifics is the primary source; fall back to title-extracted value.
    finish: getFinish(raw.itemSpecifics) || titleFinish || 'Regular',
    style: getStyle(raw.itemSpecifics) || titleStyle,
    daysListed: calcDaysListed(raw.listingDetails?.startTime),
    watchCount: raw.watchCount ?? 0,
    viewItemUrl:
      raw.listingDetails?.viewItemUrl ?? `https://www.ebay.com.au/itm/${itemId}`,
    imageUrl: getImageUrl(raw.pictureDetails),
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
    `/integrations/ebay/listing/active?app_code=${encodeURIComponent(appCode)}&limit=${limit}&offset=${offset}`
  )
  const items: RawEbayItem[] = Array.isArray(raw)
    ? raw
    : Array.isArray((raw as { data?: unknown }).data)
      ? (raw as { data: RawEbayItem[] }).data
      : []
  return items.map((item) => ({ ...mapToLiveListing(item), appCode, appName: '' }))
}

export async function fetchActiveListingsPaginated(
  appCode: string,
  limit: number,
  offset: number,
): Promise<{ items: EbayLiveListing[]; hasMore: boolean }> {
  const raw = await apiClient<unknown>(
    `/integrations/ebay/listing/active?app_code=${encodeURIComponent(appCode)}&limit=${limit}&offset=${offset}`
  )
  let items: RawEbayItem[]
  let hasMore: boolean
  if (Array.isArray(raw)) {
    items = raw
    hasMore = items.length === limit
  } else {
    const paged = raw as { data?: unknown; pagination?: { has_more?: boolean } }
    items = Array.isArray(paged.data) ? (paged.data as RawEbayItem[]) : []
    hasMore = paged.pagination?.has_more ?? items.length === limit
  }
  return {
    items: items.map((item) => ({ ...mapToLiveListing(item), appCode, appName: '' })),
    hasMore,
  }
}
