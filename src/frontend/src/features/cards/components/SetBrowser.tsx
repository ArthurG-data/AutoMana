// src/frontend/src/features/cards/components/SetBrowser.tsx
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { setBrowseQueryOptions } from '../api'
import type { SetBrowseItem } from '../types'
import styles from './SetBrowser.module.css'

const FALLBACK_ICON = (
  <svg className={styles.iconFallback} viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" fill="none"/>
  </svg>
)

type GroupBy = 'none' | 'type' | 'year'

const SET_TYPE_LABELS: Record<string, string> = {
  expansion: 'Expansion',
  core: 'Core',
  masters: 'Masters',
  commander: 'Commander',
  draft_innovation: 'Draft Innovation',
  alchemy: 'Alchemy',
  funny: 'Funny',
  promo: 'Promo',
  starter: 'Starter',
  duel_deck: 'Duel Deck',
  from_the_vault: 'From the Vault',
  premium_deck: 'Premium Deck',
  spellbook: 'Spellbook',
  archenemy: 'Archenemy',
  planechase: 'Planechase',
  vanguard: 'Vanguard',
  treasure_chest: 'Treasure Chest',
  box: 'Box Set',
  token: 'Token',
  memorabilia: 'Memorabilia',
  jumpstart: 'Jumpstart',
  minigame: 'Minigame',
}

function prettyType(t: string): string {
  return SET_TYPE_LABELS[t] ?? t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function yearOf(released?: string | null): string {
  return released ? released.slice(0, 4) : 'Unknown'
}

function SetRow({ set, onSelect }: { set: SetBrowseItem; onSelect: (code: string) => void }) {
  return (
    <button className={styles.row} onClick={() => onSelect(set.set_code)}>
      <span className={styles.icon}>
        {set.icon_svg_uri
          ? <img src={set.icon_svg_uri} alt="" aria-hidden />
          : FALLBACK_ICON}
      </span>
      <span className={styles.name}>{set.set_name}</span>
      <span className={styles.meta}>
        <span className={styles.code}>{set.set_code}</span>
        <span className={styles.type}>{prettyType(set.set_type)}</span>
      </span>
      <span className={styles.count}>{set.card_count}</span>
    </button>
  )
}

interface SetBrowserProps {
  onSelect: (setCode: string) => void
}

export function SetBrowser({ onSelect }: SetBrowserProps) {
  const { data: sets = [], isLoading, isError } = useQuery(setBrowseQueryOptions())
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set())
  const [groupBy, setGroupBy] = useState<GroupBy>('none')

  const availableTypes = useMemo(() => {
    const counts = new Map<string, number>()
    for (const s of sets) counts.set(s.set_type, (counts.get(s.set_type) ?? 0) + 1)
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
  }, [sets])

  const visible = useMemo(() => {
    if (selectedTypes.size === 0) return sets
    return sets.filter((s) => selectedTypes.has(s.set_type))
  }, [sets, selectedTypes])

  const groups = useMemo(() => {
    if (groupBy === 'none') return [{ key: '__all__', label: '', sets: visible }]
    const buckets = new Map<string, SetBrowseItem[]>()
    for (const s of visible) {
      const key = groupBy === 'type' ? s.set_type : yearOf(s.released_at)
      if (!buckets.has(key)) buckets.set(key, [])
      buckets.get(key)!.push(s)
    }
    const sortedKeys = Array.from(buckets.keys()).sort((a, b) => {
      if (groupBy === 'year') return b.localeCompare(a) // newer years first
      return a.localeCompare(b)                          // alpha for type
    })
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
        <div className={styles.controlBlock}>
          <span className={styles.controlLabel}>Type</span>
          <div className={styles.chipRow}>
            <button
              className={`${styles.chip} ${selectedTypes.size === 0 ? styles.chipActive : ''}`}
              onClick={() => setSelectedTypes(new Set())}
              type="button"
            >
              All
              <span className={styles.chipCount}>{sets.length}</span>
            </button>
            {availableTypes.map(({ type, count }) => (
              <button
                key={type}
                className={`${styles.chip} ${selectedTypes.has(type) ? styles.chipActive : ''}`}
                onClick={() => toggleType(type)}
                type="button"
              >
                {prettyType(type)}
                <span className={styles.chipCount}>{count}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.controlBlock}>
          <span className={styles.controlLabel}>Group by</span>
          <div className={styles.chipRow}>
            {(['none', 'type', 'year'] as GroupBy[]).map((g) => (
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
      ) : groupBy === 'none' ? (
        <div className={styles.list}>
          {visible.map((set) => (
            <SetRow key={set.set_code} set={set} onSelect={onSelect} />
          ))}
        </div>
      ) : (
        groups.map((g) => (
          <section key={g.key} className={styles.group}>
            <header className={styles.groupHeader}>
              <span className={styles.groupTitle}>{g.label}</span>
              <span className={styles.groupCount}>{g.sets.length}</span>
            </header>
            <div className={styles.list}>
              {g.sets.map((set) => (
                <SetRow key={set.set_code} set={set} onSelect={onSelect} />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
