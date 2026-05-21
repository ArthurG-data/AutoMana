import type { CollectionEntry } from './api'

export interface EntryGroup {
  key: string
  representative: CollectionEntry
  copies: CollectionEntry[]
}

export function groupEntries(entries: CollectionEntry[]): EntryGroup[] {
  const map = new Map<string, EntryGroup>()
  for (const entry of entries) {
    const key = entry.card_version_id
    if (!map.has(key)) {
      map.set(key, { key, representative: entry, copies: [] })
    }
    map.get(key)!.copies.push(entry)
  }
  return Array.from(map.values())
}
