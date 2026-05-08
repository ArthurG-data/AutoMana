import { apiClient } from '../../../lib/apiClient'
import type { EbayLiveListing } from '../mockListings'

interface CardSuggestion {
  card_name: string
  set_code: string
}

/**
 * Enriches eBay listings with canonical card names and set codes from the
 * AutoMana card catalog (backed by Scryfall data).
 *
 * Fires one /card-reference/suggest call per unique parsed card name, in
 * parallel. Failures are swallowed — the listing keeps its title-parsed values.
 * Listings are updated in place: cardName becomes the canonical Scryfall name,
 * setCode is filled from the catalog when the title parser couldn't find one.
 */
export async function enrichWithCatalog(
  listings: EbayLiveListing[],
): Promise<EbayLiveListing[]> {
  const uniqueNames = [
    ...new Set(listings.map((l) => l.cardName).filter((n) => n.length >= 2)),
  ]

  const settled = await Promise.allSettled(
    uniqueNames.map(async (name) => {
      const resp = await apiClient<{ suggestions: CardSuggestion[] }>(
        `/card-reference/suggest?q=${encodeURIComponent(name)}&limit=1`,
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
      // Title-extracted set code wins (user knows their specific printing);
      // catalog set code fills the gap when the title didn't have one.
      setCode: listing.setCode || hit.setCode,
    }
  })
}
