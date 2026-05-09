import { create } from 'zustand'
import type { EbayLiveListing } from '../features/ebay/mockListings'

interface ListingsState {
  listings: EbayLiveListing[]
  setListings: (listings: EbayLiveListing[]) => void
  getById: (itemId: string) => EbayLiveListing | undefined
  updateListing: (itemId: string, patch: Partial<EbayLiveListing>) => void
}

export const useListingsStore = create<ListingsState>()((set, get) => ({
  listings: [],
  setListings: (listings) => set({ listings }),
  getById: (itemId) => get().listings.find((l) => l.itemId === itemId),
  updateListing: (itemId, patch) =>
    set((state) => ({
      listings: state.listings.map((l) =>
        l.itemId === itemId ? { ...l, ...patch } : l
      ),
    })),
}))
