// src/frontend/src/features/collection/api.ts
import { queryOptions } from '@tanstack/react-query'
import { apiClient } from '../../lib/apiClient'

export interface Collection {
  collection_id: string
  collection_name: string
  description: string
  is_active: boolean
  created_at: string
  username: string
}

export type EntryStatus = 'purchased' | 'listed' | 'stashed' | 'sold'

export interface CollectionEntry {
  item_id: string
  card_version_id: string
  card_name: string
  set_code: string
  collector_number: string
  finish: 'NONFOIL' | 'FOIL' | 'ETCHED'
  condition: 'NM' | 'LP' | 'MP' | 'HP' | 'DMG' | 'SP'
  purchase_price: string
  purchase_date: string
  currency_code: string
  language_id?: number | null
  image_normal?: string | null
  price?: number | null
  price_change_1d: number
  status: EntryStatus
  ebay_item_id?: string | null
  is_wishlist: boolean
}

// ── Constants ───────────────────────────────────────────────────────────────

const PAGE_SIZE = 50

// ── Query options ────────────────────────────────────────────────────────────

export function collectionsQueryOptions() {
  return queryOptions({
    queryKey: ['collection', 'list'] as const,
    queryFn: () =>
      apiClient<Collection[]>('/catalog/mtg/collection/'),
    staleTime: 5 * 60_000,
    gcTime: 15 * 60_000,
  })
}

export function collectionEntriesQueryOptions(collectionId: string) {
  return queryOptions({
    queryKey: ['collection', 'entries', collectionId] as const,
    queryFn: () =>
      apiClient<CollectionEntry[]>(
        `/catalog/mtg/collection/${collectionId}/entries?limit=${PAGE_SIZE}&offset=0`,
      ),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    enabled: Boolean(collectionId),
  })
}

/** Fetch one page of collection entries. Used by useInfiniteEntries. */
export async function fetchEntriesPage(
  collectionId: string,
  offset: number,
  limit = PAGE_SIZE,
  isWishlist?: boolean,
): Promise<CollectionEntry[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  if (isWishlist !== undefined) {
    params.set('is_wishlist', String(isWishlist))
  }
  return apiClient<CollectionEntry[]>(
    `/catalog/mtg/collection/${collectionId}/entries?${params}`,
  )
}

// ── Mutations ────────────────────────────────────────────────────────────────

export async function createCollection(name: string): Promise<Collection> {
  return apiClient<Collection>('/catalog/mtg/collection/', {
    method: 'POST',
    body: JSON.stringify({ collection_name: name, description: '' }),
  })
}

export async function addCollectionEntry(
  collectionId: string,
  cardVersionId: string,
  condition: CollectionEntry['condition'],
  finish: CollectionEntry['finish'],
  options?: { status?: EntryStatus; ebayItemId?: string; isWishlist?: boolean },
): Promise<CollectionEntry> {
  return apiClient<CollectionEntry>(
    `/catalog/mtg/collection/${collectionId}/entries`,
    {
      method: 'POST',
      body: JSON.stringify({
        card_version_id: cardVersionId,
        condition,
        finish,
        purchase_price: '0.00',
        status: options?.status ?? 'purchased',
        ebay_item_id: options?.ebayItemId ?? null,
        is_wishlist: options?.isWishlist ?? false,
      }),
    },
  )
}

export async function updateEntryStatus(
  collectionId: string,
  entryId: string,
  status: EntryStatus,
): Promise<CollectionEntry> {
  return apiClient<CollectionEntry>(
    `/catalog/mtg/collection/${collectionId}/entries/${entryId}/status`,
    { method: 'PATCH', body: JSON.stringify({ status }) },
  )
}

export async function deleteCollectionEntry(
  collectionId: string,
  entryId: string,
): Promise<void> {
  await apiClient<void>(
    `/catalog/mtg/collection/${collectionId}/entries/${entryId}`,
    { method: 'DELETE' },
  )
}

export { PAGE_SIZE }
