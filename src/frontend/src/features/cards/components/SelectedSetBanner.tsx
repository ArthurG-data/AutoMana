// src/frontend/src/features/cards/components/SelectedSetBanner.tsx
import { useQuery } from '@tanstack/react-query'
import { setBrowseQueryOptions } from '../api'
import styles from './SelectedSetBanner.module.css'

const FALLBACK_ICON = (
  <svg className={styles.iconFallback} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
  </svg>
)

interface SelectedSetBannerProps {
  setCode: string
  onClear: () => void
}

export function SelectedSetBanner({ setCode, onClear }: SelectedSetBannerProps) {
  const { data: sets = [] } = useQuery(setBrowseQueryOptions())
  const set = sets.find(s => s.set_code === setCode)

  if (!set) {
    return (
      <div className={styles.banner}>
        <div className={styles.info}>
          <div className={styles.name}>{setCode.toUpperCase()}</div>
        </div>
        <button className={styles.changeBtn} onClick={onClear}>↩ Change set</button>
      </div>
    )
  }

  const year = set.released_at.slice(0, 4)

  return (
    <div className={styles.banner}>
      <span className={styles.icon}>
        {set.icon_svg_uri
          ? <img src={set.icon_svg_uri} alt="" aria-hidden />
          : FALLBACK_ICON}
      </span>
      <div className={styles.info}>
        <div className={styles.name}>{set.set_name}</div>
        <div className={styles.meta}>
          <span className={styles.code}>{set.set_code}</span>
          <span className={styles.type}>{set.set_type}</span>
          <span className={styles.detail}>{set.card_count} cards · {year}</span>
        </div>
      </div>
      <button className={styles.changeBtn} onClick={onClear}>↩ Change set</button>
    </div>
  )
}
