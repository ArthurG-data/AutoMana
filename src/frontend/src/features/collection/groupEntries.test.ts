import { describe, it, expect } from 'vitest'
import { groupEntries } from './groupEntries'
import type { CollectionEntry } from './api'

const makeEntry = (overrides: Partial<CollectionEntry> = {}): CollectionEntry => ({
  item_id: 'item-1',
  card_version_id: 'card-a',
  card_name: 'Sol Ring',
  set_code: 'lea',
  collector_number: '265',
  finish: 'NONFOIL',
  condition: 'NM',
  purchase_price: '5.00',
  purchase_date: '2024-01-01',
  currency_code: 'USD',
  price: null,
  price_change_1d: 0,
  status: 'purchased',
  ...overrides,
})

describe('groupEntries', () => {
  it('returns empty array for empty input', () => {
    expect(groupEntries([])).toEqual([])
  })

  it('groups entries with identical card_version_id regardless of finish or condition', () => {
    const entries = [
      makeEntry({ item_id: 'item-1' }),
      makeEntry({ item_id: 'item-2' }),
      makeEntry({ item_id: 'item-3' }),
    ]
    const groups = groupEntries(entries)
    expect(groups).toHaveLength(1)
    expect(groups[0].copies).toHaveLength(3)
  })

  it('groups copies with different conditions into one tile', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', condition: 'NM' }),
      makeEntry({ item_id: 'item-2', condition: 'LP' }),
    ]
    expect(groupEntries(entries)).toHaveLength(1)
    expect(groupEntries(entries)[0].copies).toHaveLength(2)
  })

  it('groups copies with different finishes into one tile', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', finish: 'NONFOIL' }),
      makeEntry({ item_id: 'item-2', finish: 'FOIL' }),
    ]
    expect(groupEntries(entries)).toHaveLength(1)
    expect(groupEntries(entries)[0].copies).toHaveLength(2)
  })

  it('creates separate groups for different card_version_ids', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', card_version_id: 'card-a' }),
      makeEntry({ item_id: 'item-2', card_version_id: 'card-b' }),
    ]
    expect(groupEntries(entries)).toHaveLength(2)
  })

  it('sets representative to the first entry in the group', () => {
    const entries = [makeEntry({ item_id: 'item-1' }), makeEntry({ item_id: 'item-2' })]
    expect(groupEntries(entries)[0].representative.item_id).toBe('item-1')
  })

  it('groups interleaved entries into the same bucket', () => {
    const entries = [
      makeEntry({ item_id: 'item-1', card_version_id: 'card-a' }),
      makeEntry({ item_id: 'item-2', card_version_id: 'card-b' }),
      makeEntry({ item_id: 'item-3', card_version_id: 'card-a' }),
    ]
    const groups = groupEntries(entries)
    expect(groups).toHaveLength(2)
    expect(groups[0].copies.map((c) => c.item_id)).toEqual(['item-1', 'item-3'])
    expect(groups[1].copies.map((c) => c.item_id)).toEqual(['item-2'])
  })

  it('builds key as card_version_id only', () => {
    const entries = [makeEntry({ card_version_id: 'card-x', finish: 'FOIL', condition: 'LP' })]
    expect(groupEntries(entries)[0].key).toBe('card-x')
  })
})
