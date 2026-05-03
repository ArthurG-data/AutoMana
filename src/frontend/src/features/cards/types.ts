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
  mana_cost?: string
  type_line?: string
  oracle_text?: string
  artist?: string
  price_history?: number[]
  prints?: CardPrint[]
  image_large?: string | null
}

export interface CardSearchParams {
  q?: string
  set?: string
  rarity?: string
  finish?: string
  minPrice?: number
  maxPrice?: number
  page?: number
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
