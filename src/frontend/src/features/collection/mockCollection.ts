// src/frontend/src/features/collection/mockCollection.ts
// TODO: replace with useQuery(collectionQueryOptions) when /api/catalog/mtg/collection/ is wired

import type { AIStatus } from '../../components/design-system/AIBadge'
import type { ManaColor } from '../../components/design-system/Pip'

export interface CollectionCard {
  id: string
  name: string
  set: string
  setCode: string
  qty: number
  costBasis: number      // per-card cost in USD
  marketPrice: number    // current market price in USD
  peak30d: number        // 30-day peak price
  colors: ManaColor[]
  aiStatus: AIStatus
  foil: boolean
}

export interface CollectionMetrics {
  totalValue: number
  costBasis: number
  unrealizedPL: number
  cardsOwned: number
  listedOnEbay: number
}

export const MOCK_COLLECTION: CollectionCard[] = [
  {
    id: 'c1',
    name: 'Ragavan, Nimble Pilferer',
    set: 'Modern Horizons 2',
    setCode: 'MH2',
    qty: 4,
    costBasis: 28.00,
    marketPrice: 54.20,
    peak30d: 61.50,
    colors: ['R'],
    aiStatus: 'ready',
    foil: false,
  },
  {
    id: 'c2',
    name: 'Wrenn and Six',
    set: 'Modern Horizons',
    setCode: 'MH1',
    qty: 2,
    costBasis: 42.00,
    marketPrice: 38.75,
    peak30d: 45.00,
    colors: ['R', 'G'],
    aiStatus: 'watching',
    foil: false,
  },
  {
    id: 'c3',
    name: 'Force of Will',
    set: 'Alliances',
    setCode: 'ALL',
    qty: 1,
    costBasis: 95.00,
    marketPrice: 112.50,
    peak30d: 118.00,
    colors: ['U'],
    aiStatus: 'listed',
    foil: false,
  },
  {
    id: 'c4',
    name: 'Liliana of the Veil',
    set: 'Innistrad',
    setCode: 'ISD',
    qty: 3,
    costBasis: 55.00,
    marketPrice: 49.80,
    peak30d: 58.20,
    colors: ['B'],
    aiStatus: 'watching',
    foil: false,
  },
  {
    id: 'c5',
    name: 'Sheoldred, the Apocalypse',
    set: 'Dominaria United',
    setCode: 'DMU',
    qty: 4,
    costBasis: 34.00,
    marketPrice: 47.60,
    peak30d: 51.00,
    colors: ['B'],
    aiStatus: 'ready',
    foil: false,
  },
  {
    id: 'c6',
    name: 'Mox Diamond',
    set: 'Stronghold',
    setCode: 'STH',
    qty: 1,
    costBasis: 280.00,
    marketPrice: 310.00,
    peak30d: 325.00,
    colors: ['C'],
    aiStatus: 'vault',
    foil: false,
  },
  {
    id: 'c7',
    name: 'Emrakul, the Aeons Torn',
    set: 'Rise of the Eldrazi',
    setCode: 'ROE',
    qty: 1,
    costBasis: 18.00,
    marketPrice: 22.40,
    peak30d: 24.80,
    colors: ['C'],
    aiStatus: 'listed',
    foil: false,
  },
  {
    id: 'c8',
    name: 'Teferi, Time Raveler',
    set: 'War of the Spark',
    setCode: 'WAR',
    qty: 2,
    costBasis: 9.50,
    marketPrice: 11.20,
    peak30d: 12.60,
    colors: ['W', 'U'],
    aiStatus: 'ready',
    foil: false,
  },
  {
    id: 'c9',
    name: 'Ancient Tomb',
    set: 'Tempest',
    setCode: 'TMP',
    qty: 2,
    costBasis: 62.00,
    marketPrice: 59.40,
    peak30d: 68.00,
    colors: ['C'],
    aiStatus: 'vault',
    foil: false,
  },
  {
    id: 'c10',
    name: 'Craterhoof Behemoth',
    set: 'Avacyn Restored',
    setCode: 'AVR',
    qty: 3,
    costBasis: 16.50,
    marketPrice: 21.80,
    peak30d: 23.50,
    colors: ['G'],
    aiStatus: 'watching',
    foil: false,
  },
]

export function computeMetrics(cards: CollectionCard[]): CollectionMetrics {
  let totalValue = 0
  let costBasis = 0
  let listedOnEbay = 0
  let cardsOwned = 0

  for (const card of cards) {
    totalValue  += card.marketPrice * card.qty
    costBasis   += card.costBasis * card.qty
    cardsOwned  += card.qty
    if (card.aiStatus === 'listed') listedOnEbay += card.qty
  }

  return {
    totalValue,
    costBasis,
    unrealizedPL: totalValue - costBasis,
    cardsOwned,
    listedOnEbay,
  }
}

export function formatUSD(value: number): string {
  const abs = Math.abs(value)
  const formatted = abs >= 1000
    ? `$${(abs / 1000).toFixed(1)}k`
    : `$${abs.toFixed(2)}`
  return value < 0 ? `-${formatted}` : formatted
}

export type StatusFilter = 'all' | AIStatus
export type ColorFilter = ManaColor | 'all'
