// src/frontend/src/features/cards/types.ts

export interface CardSummary {
  card_version_id: string
  card_name: string
  set_code: string
  set_name: string
  finish: 'non-foil' | 'foil' | 'etched'
  rarity_name: 'common' | 'uncommon' | 'rare' | 'mythic'
  price?: number
  price_change_1d: number
  price_change_7d: number
  price_change_30d: number
  image_uri: string | null
  image_normal?: string | null
  spark: number[]
}

export interface CardPrint {
  id: string
  set: string
  set_name: string
  finish: 'non-foil' | 'foil' | 'etched'
  price: number
  image_uri: string | null
}

export interface CardDetail extends CardSummary {
  unique_card_id?: string
  mana_cost?: string
  type_line?: string
  oracle_text?: string
  artist?: string
  price_history?: number[]
  prints?: CardPrint[]
  image_large?: string | null
  price_history_list_avg?: number[]
  price_history_sold_avg?: number[]
  available_finishes?: string[]
  is_multifaced?: boolean
  card_back_id?: string | null
  back_face_image_uri?: string | null
  collector_number?: string
  promo_types?: string[]
  legalities?: Record<string, string>
}

export type CardGroupBy = 'set' | 'rarity' | 'finish'

export interface CardSearchParams {
  q?: string
  set?: string
  artist?: string
  unique_card_id?: string
  rarity?: string
  finish?: string
  layout?: string
  minPrice?: number
  maxPrice?: number
  promoTypes?: string[]
  group?: CardGroupBy
}

export interface PaginationInfo {
  limit: number
  offset: number
  total_count: number
  has_next: boolean
  has_previous: boolean
}

export interface CardSearchResponse {
  cards: any[] // Actual backend returns different card format
  total: number
  page?: number
  per_page?: number
  pagination?: PaginationInfo
}

export interface CardSuggestion {
  card_version_id: string
  card_name: string
  set_code: string
  collector_number: string
  rarity_name: string
  scryfall_id?: string
  score: number
}

export interface CardSuggestParams {
  q: string
  limit?: number
}

export interface CardSuggestResponse {
  suggestions: CardSuggestion[]
}

export interface CatalogStats {
  total_card_versions: number
  data_source: string
  last_updated: string | null
}

export interface SetBrowseItem {
  set_id: string
  set_name: string
  set_code: string
  set_type: string
  card_count: number
  released_at: string
  icon_svg_uri: string | null
  parent_set_code: string | null
}
