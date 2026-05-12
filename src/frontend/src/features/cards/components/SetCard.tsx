import { useState } from 'react'
import type { SetBrowseItem } from '../types'
import styles from './SetCard.module.css'

function iconUrl(set: SetBrowseItem): string {
  return set.icon_svg_uri || `https://svgs.scryfall.io/sets/${set.set_code.toLowerCase()}.svg`
}

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

function prettyType(t: string): string {
  const labels: Record<string, string> = {
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
  return labels[t] ?? t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

interface SetCardProps {
  set: SetBrowseItem
  isChild?: boolean
  onSelect: (code: string) => void
}

export function SetCard({ set, isChild = false, onSelect }: SetCardProps) {
  const [iconBroken, setIconBroken] = useState(false)

  return (
    <button
      className={`${styles.card} ${isChild ? styles.childCard : ''}`}
      onClick={() => onSelect(set.set_code)}
      type="button"
      title={set.set_name}
    >
      {/* Art area — same aspect ratio as MTG card art in SearchResults */}
      <div className={styles.art}>
        <div className={styles.artInner}>
          {set.key_art_uri && (
            <div
              className={styles.bgArt}
              style={{ backgroundImage: `url("${set.key_art_uri}")` }}
            />
          )}
          {iconBroken ? (
            <svg className={styles.iconFallback} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          ) : (
            <img
              className={styles.iconImg}
              src={iconUrl(set)}
              alt=""
              aria-hidden
              onError={() => setIconBroken(true)}
            />
          )}
          <div className={styles.setName}>{set.set_name}</div>
        </div>
      </div>

      {/* Info bar — mirrors .cardInfo in SearchResults */}
      <div className={styles.info}>
        <div className={styles.codeRow}>
          <span className={styles.code}>{set.set_code.toUpperCase()}</span>
          <span className={styles.date}>{formatDate(set.released_at)}</span>
        </div>
        <div className={styles.meta}>
          <span className={styles.type}>{prettyType(set.set_type)}</span>
          <span className={styles.count}>{set.card_count}</span>
        </div>
      </div>
    </button>
  )
}
