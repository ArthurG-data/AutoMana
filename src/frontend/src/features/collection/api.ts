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
}

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
      apiClient<CollectionEntry[]>(`/catalog/mtg/collection/${collectionId}/entries`),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    enabled: Boolean(collectionId),
  })
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
      }),
    },
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
