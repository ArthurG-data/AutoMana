// src/frontend/src/features/cards/types.ts

export interface CardSummary {
  id: string
  name: string
  set: string
  set_name: string
  finish: 'non-foil' | 'foil' | 'etched'
  rarity: 'common' | 'uncommon' | 'rare' | 'mythic'
  price: number
  price_change_1d: number
  price_change_7d: number
  price_change_30d: number
  image_uri: string | null
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
  mana_cost: string
  type_line: string
  oracle_text: string
  artist: string
  price_history: number[]
  prints: CardPrint[]
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

export interface CardSearchResponse {
  cards: CardSummary[]
  total: number
  page: number
  per_page: number
}

export interface CardSuggestion {
  id: string
  name: string
  set: string
}

export interface CardSuggestParams {
  q: string
  limit?: number
}

export interface CardSuggestResponse {
  suggestions: CardSuggestion[]
}
