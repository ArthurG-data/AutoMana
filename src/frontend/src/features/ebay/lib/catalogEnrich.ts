import type { QueryClient } from '@tanstack/react-query'
import { cardSuggestQueryOptions } from '../../cards/api'
import type { EbayLiveListing } from '../mockListings'

/**
 * Enriches eBay listings with canonical card names and set codes from the
 * AutoMana card catalog (backed by Scryfall data).
 *
 * Uses queryClient.fetchQuery so React Query deduplicates concurrent calls for
 * the same card name and caches results for 24h — eliminating the redundant
 * API calls that fired on every previous mount.
 */
export async function enrichWithCatalog(
  listings: EbayLiveListing[],
  queryClient: QueryClient,
): Promise<EbayLiveListing[]> {
  const uniqueNames = [
    ...new Set(listings.map((l) => l.cardName).filter((n) => n.length >= 2)),
  ]

  const settled = await Promise.allSettled(
    uniqueNames.map(async (name) => {
      const resp = await queryClient.fetchQuery(
        cardSuggestQueryOptions({ q: name, limit: 1 }),
      )
      const first = resp.suggestions?.[0]
      return {
        key: name.toLowerCase(),
        cardName: first?.card_name ?? name,
        setCode: first?.set_code?.toUpperCase() ?? '',
      }
    }),
  )

  const lookup = new Map<string, { cardName: string; setCode: string }>()
  for (const r of settled) {
    if (r.status === 'fulfilled') {
      lookup.set(r.value.key, {
        cardName: r.value.cardName,
        setCode: r.value.setCode,
      })
    }
  }

  return listings.map((listing) => {
    const hit = lookup.get(listing.cardName.toLowerCase())
    if (!hit) return listing
    return {
      ...listing,
      cardName: hit.cardName,
      setCode: listing.setCode || hit.setCode,
    }
  })
}
