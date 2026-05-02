// src/frontend/src/features/cards/components/SearchResults.tsx
import { useNavigate } from '@tanstack/react-router'
import { CardArt } from '../../../components/design-system/CardArt'
import { Sparkline } from '../../../components/design-system/Sparkline'
import type { CardSummary } from '../types'
import styles from './SearchResults.module.css'

interface SearchResultsProps {
  cards: CardSummary[]
  total: number
}

export function SearchResults({ cards, total }: SearchResultsProps) {
  const navigate = useNavigate()

  if (cards.length === 0) {
    return <div className={styles.empty}>No cards found. Try a different search.</div>
  }

  return (
    <div className={styles.results}>
      <div className={styles.meta}>{total.toLocaleString()} results</div>
      <div className={styles.grid}>
        {cards.map((card, i) => {
          const delta = card.price_change_1d
          return (
            <button
              key={card.id}
              className={styles.card}
              onClick={() => navigate({ to: '/cards/$id', params: { id: card.id } })}
            >
              <CardArt name={card.card_name} w="100%" h={195} hue={(i * 47) % 360} label={false} />
              <div className={styles.cardInfo}>
                <div className={styles.cardName}>{card.card_name}</div>
                <div className={styles.cardMeta}>
                  <span className={styles.set}>{card.set}</span>
                  <span className={[styles.price, delta >= 0 ? styles.up : styles.down].join(' ')}>
                    {card.price != null ? `$${card.price.toFixed(2)}` : 'N/A'}
                  </span>
                </div>
                <Sparkline
                  points={card.spark}
                  color={delta >= 0 ? 'var(--hd-accent)' : 'var(--hd-red)'}
                  width={100}
                  height={24}
                />
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
