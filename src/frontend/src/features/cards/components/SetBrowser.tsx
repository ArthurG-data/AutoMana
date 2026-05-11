// src/frontend/src/features/cards/components/SetBrowser.tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { setBrowseQueryOptions } from '../api'
import type { SetBrowseItem } from '../types'
import styles from './SetBrowser.module.css'

const FALLBACK_ICON = (
  <svg className={styles.iconFallback} viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" fill="none"/>
  </svg>
)

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
        <span className={styles.type}>{set.set_type}</span>
      </span>
      <span className={styles.count}>{set.card_count}</span>
    </button>
  )
}

interface SetBrowserProps {
  onSelect: (setCode: string) => void
}

export function SetBrowser({ onSelect }: SetBrowserProps) {
  const [filter, setFilter] = useState('')
  const { data: sets = [], isError } = useQuery(setBrowseQueryOptions())

  const filtered = filter.trim()
    ? sets.filter(s =>
        s.set_name.toLowerCase().includes(filter.toLowerCase()) ||
        s.set_code.toLowerCase().includes(filter.toLowerCase())
      )
    : sets

  if (isError) {
    return (
      <div className={styles.wrap}>
        <p className={styles.empty}>Failed to load sets. Please refresh.</p>
      </div>
    )
  }

  return (
    <div className={styles.wrap}>
      <input
        className={styles.filterInput}
        placeholder="Filter sets…"
        value={filter}
        onChange={e => setFilter(e.target.value)}
        aria-label="Filter sets by name or code"
      />
      <div className={styles.list}>
        {filtered.length === 0
          ? <p className={styles.empty}>No sets match "{filter}"</p>
          : filtered.map(set => (
              <SetRow key={set.set_code} set={set} onSelect={onSelect} />
            ))
        }
      </div>
    </div>
  )
}
