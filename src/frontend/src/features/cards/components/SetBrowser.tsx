// src/frontend/src/features/cards/components/SetBrowser.tsx
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { setBrowseQueryOptions } from '../api'
import type { SetBrowseItem } from '../types'
import { SetCard } from './SetCard'
import styles from './SetBrowser.module.css'

type GroupBy = 'none' | 'type' | 'year'

const SET_TYPE_LABELS: Record<string, string> = {
  expansion: 'Expansion', core: 'Core', masters: 'Masters',
  commander: 'Commander', draft_innovation: 'Draft Innovation',
  alchemy: 'Alchemy', funny: 'Funny', promo: 'Promo',
  starter: 'Starter', duel_deck: 'Duel Deck',
  from_the_vault: 'From the Vault', premium_deck: 'Premium Deck',
  spellbook: 'Spellbook', archenemy: 'Archenemy',
  planechase: 'Planechase', vanguard: 'Vanguard',
  treasure_chest: 'Treasure Chest', box: 'Box Set',
  token: 'Token', memorabilia: 'Memorabilia',
  jumpstart: 'Jumpstart', minigame: 'Minigame',
}

function prettyType(t: string): string {
  return SET_TYPE_LABELS[t] ?? t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function yearOf(released?: string | null): string {
  return released ? released.slice(0, 4) : 'Unknown'
}

interface SetGroup {
  parent: SetBrowseItem
  children: SetBrowseItem[]
}

function groupByParentChild(sets: SetBrowseItem[]): SetGroup[] {
  const byCode = new Map(sets.map((s) => [s.set_code, s]))
  const childrenOf = new Map<string, SetBrowseItem[]>()
  const processedAsChild = new Set<string>()

  for (const s of sets) {
    if (s.parent_set_code && byCode.has(s.parent_set_code)) {
      if (!childrenOf.has(s.parent_set_code)) childrenOf.set(s.parent_set_code, [])
      childrenOf.get(s.parent_set_code)!.push(s)
      processedAsChild.add(s.set_code)
    }
  }

  const groups: SetGroup[] = []
  for (const s of sets) {
    if (processedAsChild.has(s.set_code)) continue
    groups.push({ parent: s, children: childrenOf.get(s.set_code) ?? [] })
  }
  return groups
}

interface SetBrowserProps {
  onSelect: (setCode: string) => void
}

export function SetBrowser({ onSelect }: SetBrowserProps) {
  const { data: sets = [], isLoading, isError } = useQuery(setBrowseQueryOptions())
  const [search, setSearch] = useState('')
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set())
  const [groupBy, setGroupBy] = useState<GroupBy>('year')

  const availableTypes = useMemo(() => {
    const counts = new Map<string, number>()
    for (const s of sets) counts.set(s.set_type, (counts.get(s.set_type) ?? 0) + 1)
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
  }, [sets])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    return sets.filter((s) => {
      if (selectedTypes.size > 0 && !selectedTypes.has(s.set_type)) return false
      if (q && !s.set_name.toLowerCase().includes(q) && !s.set_code.toLowerCase().includes(q)) return false
      return true
    })
  }, [sets, selectedTypes, search])

  const groups = useMemo(() => {
    if (groupBy === 'none') return [{ key: '__all__', label: '', sets: visible }]
    const buckets = new Map<string, SetBrowseItem[]>()
    for (const s of visible) {
      const key = groupBy === 'type' ? s.set_type : yearOf(s.released_at)
      if (!buckets.has(key)) buckets.set(key, [])
      buckets.get(key)!.push(s)
    }
    const sortedKeys = Array.from(buckets.keys()).sort((a, b) =>
      groupBy === 'year' ? b.localeCompare(a) : a.localeCompare(b)
    )
    return sortedKeys.map((key) => ({
      key,
      label: groupBy === 'type' ? prettyType(key) : key,
      sets: buckets.get(key)!,
    }))
  }, [visible, groupBy])

  function toggleType(t: string) {
    setSelectedTypes((prev) => {
      const next = new Set(prev)
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })
  }

  if (isError) {
    return (
      <div className={styles.wrap}>
        <p className={styles.empty}>Failed to load sets. Please refresh.</p>
      </div>
    )
  }

  return (
    <div className={styles.wrap}>
      <header className={styles.hero}>
        <h1 className={styles.heroTitle}>Browse Magic Sets</h1>
        <span className={styles.heroAccent} aria-hidden />
        <p className={styles.heroSub}>
          {isLoading
            ? 'Loading…'
            : (
              <>
                <strong>{visible.length.toLocaleString()}</strong>
                {selectedTypes.size > 0 && ` of ${sets.length.toLocaleString()}`}
                {' '}sets
              </>
            )}
        </p>
      </header>

      <div className={styles.controls}>
        <div className={styles.searchRow}>
          <svg className={styles.searchIcon} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <circle cx="11" cy="11" r="7"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            className={styles.searchInput}
            placeholder="Search sets by name or code…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search sets"
          />
          {search && (
            <button type="button" className={styles.searchClear} onClick={() => setSearch('')} aria-label="Clear search">
              ×
            </button>
          )}
        </div>

        <div className={styles.controlBlock}>
          <span className={styles.controlLabel}>Type</span>
          <div className={styles.chipRow}>
            <button
              className={`${styles.chip} ${selectedTypes.size === 0 ? styles.chipActive : ''}`}
              onClick={() => setSelectedTypes(new Set())}
              type="button"
            >
              All<span className={styles.chipCount}>{sets.length}</span>
            </button>
            {availableTypes.map(({ type, count }) => (
              <button
                key={type}
                className={`${styles.chip} ${selectedTypes.has(type) ? styles.chipActive : ''}`}
                onClick={() => toggleType(type)}
                type="button"
              >
                {prettyType(type)}<span className={styles.chipCount}>{count}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.controlBlock}>
          <span className={styles.controlLabel}>Group by</span>
          <div className={styles.chipRow}>
            {(['year', 'type', 'none'] as GroupBy[]).map((g) => (
              <button
                key={g}
                className={`${styles.chip} ${groupBy === g ? styles.chipActive : ''}`}
                onClick={() => setGroupBy(g)}
                type="button"
              >
                {g === 'none' ? 'None' : g === 'type' ? 'Type' : 'Year'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {visible.length === 0 ? (
        <p className={styles.empty}>No sets match the current filters.</p>
      ) : (
        groups.map((g) => (
          <section key={g.key} className={styles.group}>
            {g.key !== '__all__' && (
              <header className={styles.groupHeader}>
                <span className={styles.groupTitle}>{g.label}</span>
                <span className={styles.groupCount}>{g.sets.length}</span>
              </header>
            )}
            <div className={styles.grid}>
              {groupByParentChild(g.sets).map((group) => (
                <div key={group.parent.set_code} className={styles.parentGroup}>
                  <SetCard set={group.parent} onSelect={onSelect} />
                  {group.children.length > 0 && (
                    <div className={styles.childrenRow}>
                      {group.children.map((child) => (
                        <SetCard key={child.set_code} set={child} isChild onSelect={onSelect} />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
