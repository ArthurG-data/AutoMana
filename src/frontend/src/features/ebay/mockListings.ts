// src/frontend/src/features/ebay/mockListings.ts
// TODO: replace with useQuery(listingsQueryOptions) when /api/ebay/listings/ is wired

import type { AIStatus } from '../../components/design-system/AIBadge'

export type ListingTab = 'active' | 'sold' | 'saved'

export interface MarketBand {
  low: number
  p25: number
  median: number
  p75: number
  high: number
}

export interface ActiveListing {
  id: string
  cardName: string
  set: string
  setCode: string
  condition: string
  listedPrice: number
  marketPrice: number
  marketBand: MarketBand
  watchers: number
  daysListed: number
  views: number
  costBasis: number
  aiStatus: AIStatus
  foil: boolean
  imageUrl: string
}

export interface SoldListing {
  id: string
  cardName: string
  set: string
  setCode: string
  condition: string
  salePrice: number
  marketPriceAtSale: number
  soldDate: string    // ISO date string
  daysListed: number
  foil: boolean
}

export interface AttentionAlert {
  id: string
  type: 'overpriced' | 'stale' | 'underpriced'
  cardName: string
  message: string
  listingId: string
}

export interface StrategyMixItem {
  label: string
  color: string
  count: number
}

// ── Active listings (10 cards) ─────────────────────────────────────────────

export const MOCK_ACTIVE_LISTINGS: ActiveListing[] = [
  {
    id: 'l1',
    cardName: 'Ragavan, Nimble Pilferer',
    set: 'Modern Horizons 2',
    setCode: 'MH2',
    condition: 'NM',
    listedPrice: 62.00,
    marketPrice: 54.20,
    marketBand: { low: 48.00, p25: 52.00, median: 54.20, p75: 57.50, high: 65.00 },
    watchers: 12,
    daysListed: 3,
    views: 87,
    costBasis: 28.00,
    aiStatus: 'over',
    foil: false,
    imageUrl: '',
  },
  {
    id: 'l2',
    cardName: 'Force of Will',
    set: 'Alliances',
    setCode: 'ALL',
    condition: 'LP',
    listedPrice: 112.00,
    marketPrice: 112.50,
    marketBand: { low: 98.00, p25: 108.00, median: 112.50, p75: 118.00, high: 130.00 },
    watchers: 8,
    daysListed: 7,
    views: 210,
    costBasis: 95.00,
    aiStatus: 'ok',
    foil: false,
    imageUrl: '',
  },
  {
    id: 'l3',
    cardName: 'Sheoldred, the Apocalypse',
    set: 'Dominaria United',
    setCode: 'DMU',
    condition: 'NM',
    listedPrice: 44.00,
    marketPrice: 47.60,
    marketBand: { low: 40.00, p25: 44.50, median: 47.60, p75: 51.00, high: 55.00 },
    watchers: 5,
    daysListed: 9,
    views: 143,
    costBasis: 34.00,
    aiStatus: 'under',
    foil: false,
    imageUrl: '',
  },
  {
    id: 'l4',
    cardName: 'Wrenn and Six',
    set: 'Modern Horizons',
    setCode: 'MH1',
    condition: 'NM',
    listedPrice: 39.00,
    marketPrice: 38.75,
    marketBand: { low: 34.00, p25: 37.00, median: 38.75, p75: 41.00, high: 46.00 },
    watchers: 3,
    daysListed: 14,
    views: 65,
    costBasis: 42.00,
    aiStatus: 'ok',
    foil: false,
    imageUrl: '',
  },
  {
    id: 'l5',
    cardName: 'Teferi, Time Raveler',
    set: 'War of the Spark',
    setCode: 'WAR',
    condition: 'MP',
    listedPrice: 10.50,
    marketPrice: 11.20,
    marketBand: { low: 9.00, p25: 10.20, median: 11.20, p75: 12.00, high: 13.50 },
    watchers: 2,
    daysListed: 21,
    views: 38,
    costBasis: 9.50,
    aiStatus: 'stale',
    foil: false,
    imageUrl: '',
  },
  {
    id: 'l6',
    cardName: 'Liliana of the Veil',
    set: 'Innistrad',
    setCode: 'ISD',
    condition: 'NM',
    listedPrice: 51.00,
    marketPrice: 49.80,
    marketBand: { low: 43.00, p25: 47.00, median: 49.80, p75: 53.00, high: 60.00 },
    watchers: 7,
    daysListed: 2,
    views: 95,
    costBasis: 55.00,
    aiStatus: 'revised',
    foil: false,
    imageUrl: '',
  },
  {
    id: 'l7',
    cardName: 'Emrakul, the Aeons Torn',
    set: 'Rise of the Eldrazi',
    setCode: 'ROE',
    condition: 'NM',
    listedPrice: 22.00,
    marketPrice: 22.40,
    marketBand: { low: 18.00, p25: 20.50, median: 22.40, p75: 24.00, high: 27.00 },
    watchers: 11,
    daysListed: 5,
    views: 172,
    costBasis: 18.00,
    aiStatus: 'ok',
    foil: false,
    imageUrl: '',
  },
  {
    id: 'l8',
    cardName: 'Craterhoof Behemoth',
    set: 'Avacyn Restored',
    setCode: 'AVR',
    condition: 'LP',
    listedPrice: 20.00,
    marketPrice: 21.80,
    marketBand: { low: 17.00, p25: 19.50, median: 21.80, p75: 23.50, high: 26.00 },
    watchers: 4,
    daysListed: 11,
    views: 54,
    costBasis: 16.50,
    aiStatus: 'under',
    foil: false,
    imageUrl: '',
  },
  {
    id: 'l9',
    cardName: 'Mox Diamond (Foil)',
    set: 'Stronghold',
    setCode: 'STH',
    condition: 'NM',
    listedPrice: 1200.00,
    marketPrice: 1150.00,
    marketBand: { low: 1050.00, p25: 1100.00, median: 1150.00, p75: 1220.00, high: 1350.00 },
    watchers: 19,
    daysListed: 30,
    views: 420,
    costBasis: 900.00,
    aiStatus: 'stale',
    foil: true,
    imageUrl: '',
  },
  {
    id: 'l10',
    cardName: 'Ancient Tomb',
    set: 'Tempest',
    setCode: 'TMP',
    condition: 'MP',
    listedPrice: 58.00,
    marketPrice: 59.40,
    marketBand: { low: 52.00, p25: 56.00, median: 59.40, p75: 63.00, high: 72.00 },
    watchers: 6,
    daysListed: 8,
    views: 119,
    costBasis: 62.00,
    aiStatus: 'revised',
    foil: false,
    imageUrl: '',
  },
]

// ── Sold listings (last 3) ─────────────────────────────────────────────────

export const MOCK_SOLD_LISTINGS: SoldListing[] = [
  {
    id: 's1',
    cardName: 'Dark Confidant',
    set: 'Ravnica',
    setCode: 'RAV',
    condition: 'NM',
    salePrice: 32.50,
    marketPriceAtSale: 30.80,
    soldDate: '2026-04-30',
    daysListed: 4,
    foil: false,
  },
  {
    id: 's2',
    cardName: 'Snapcaster Mage',
    set: 'Innistrad',
    setCode: 'ISD',
    condition: 'LP',
    salePrice: 18.00,
    marketPriceAtSale: 19.20,
    soldDate: '2026-04-27',
    daysListed: 7,
    foil: false,
  },
  {
    id: 's3',
    cardName: 'Vendilion Clique',
    set: 'Morningtide',
    setCode: 'MOR',
    condition: 'NM',
    salePrice: 14.75,
    marketPriceAtSale: 13.90,
    soldDate: '2026-04-24',
    daysListed: 2,
    foil: false,
  },
]

// ── Attention alerts ───────────────────────────────────────────────────────

export const MOCK_ATTENTION_ALERTS: AttentionAlert[] = [
  {
    id: 'a1',
    type: 'overpriced',
    cardName: 'Ragavan, Nimble Pilferer',
    message: 'Listed 14% above market — 0 bids in 3 days',
    listingId: 'l1',
  },
  {
    id: 'a2',
    type: 'stale',
    cardName: 'Mox Diamond (Foil)',
    message: 'No activity in 30 days — consider repricing',
    listingId: 'l9',
  },
  {
    id: 'a3',
    type: 'underpriced',
    cardName: 'Sheoldred, the Apocalypse',
    message: 'Priced 8% below median — potential money left on table',
    listingId: 'l3',
  },
]

// ── Strategy mix data ──────────────────────────────────────────────────────

export const MOCK_STRATEGY_MIX: StrategyMixItem[] = [
  { label: 'Quick sale',   color: 'var(--hd-accent)', count: 2 },
  { label: 'Balanced',     color: 'var(--hd-blue)',   count: 4 },
  { label: 'Max return',   color: 'var(--hd-amber)',  count: 3 },
  { label: 'Auction 7d',   color: '#a78bfa',          count: 1 },
]

// ── Utilities ─────────────────────────────────────────────────────────────

export function formatUSD(value: number): string {
  const abs = Math.abs(value)
  const formatted =
    abs >= 1000
      ? `$${(abs / 1000).toFixed(1)}k`
      : `$${abs.toFixed(2)}`
  return value < 0 ? `-${formatted}` : formatted
}

export function priceDeltaPct(listed: number, market: number): number {
  if (market === 0) return 0
  return Math.round(((listed - market) / market) * 100)
}

export function feeEstimate(price: number): number {
  // Rough eBay + PayPal combined (~13.25%)
  return price * (1 - 0.1325)
}
