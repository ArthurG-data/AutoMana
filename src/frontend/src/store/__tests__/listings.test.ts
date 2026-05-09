import { describe, it, expect, beforeEach } from 'vitest'
import { useListingsStore } from '../listings'
import type { EbayLiveListing } from '../../features/ebay/mockListings'

function makeListing(overrides: Partial<EbayLiveListing> = {}): EbayLiveListing {
  return {
    itemId: 'l1',
    title: 'Ragavan MH2 NM',
    cardName: 'Ragavan',
    setCode: 'MH2',
    setInfo: 'MH2',
    price: 60,
    currency: 'AUD',
    conditionLabel: 'NM',
    finish: 'Regular',
    style: '',
    daysListed: 5,
    watchCount: 3,
    viewItemUrl: 'https://ebay.com.au/itm/l1',
    imageUrl: null,
    appCode: 'app1',
    appName: 'App 1',
    ...overrides,
  }
}

beforeEach(() => {
  useListingsStore.setState({ listings: [] })
})

describe('listings store', () => {
  it('setListings replaces all listings', () => {
    const l = makeListing()
    useListingsStore.getState().setListings([l])
    expect(useListingsStore.getState().listings).toHaveLength(1)
  })

  it('getById returns the matching listing', () => {
    useListingsStore.getState().setListings([makeListing({ itemId: 'abc' })])
    expect(useListingsStore.getState().getById('abc')?.itemId).toBe('abc')
  })

  it('getById returns undefined for unknown id', () => {
    useListingsStore.getState().setListings([makeListing()])
    expect(useListingsStore.getState().getById('nope')).toBeUndefined()
  })

  it('updateListing patches only the matching entry', () => {
    const l1 = makeListing({ itemId: 'l1', price: 60 })
    const l2 = makeListing({ itemId: 'l2', price: 10 })
    useListingsStore.getState().setListings([l1, l2])

    useListingsStore.getState().updateListing('l1', { price: 75, conditionLabel: 'LP' })

    const updated = useListingsStore.getState().listings
    expect(updated[0].price).toBe(75)
    expect(updated[0].conditionLabel).toBe('LP')
    expect(updated[1].price).toBe(10)
  })
})
