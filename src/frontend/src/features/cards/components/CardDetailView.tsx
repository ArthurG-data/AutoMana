// src/frontend/src/features/cards/components/CardDetailView.tsx
import { useState } from 'react'
import { FlippableCardArt } from '../../../components/design-system/FlippableCardArt'
import { buildScryfallBackUrl } from '../utils/scryfallBackUrl'
import { Button } from '../../../components/ui/Button'
import { PriceCharts } from './PriceCharts'
import { GameInfoCard } from './GameInfoCard'
import { MarketCard } from './MarketCard'
import { LegalityGrid } from './LegalityGrid'
import type { CardDetail } from '../types'
import styles from './CardDetailView.module.css'

interface CardDetailViewProps {
  card: CardDetail
}

export function CardDetailView({ card }: CardDetailViewProps) {
  const finishes = card.available_finishes?.length ? card.available_finishes : ['nonfoil']
  const [selectedFinish, setSelectedFinish] = useState(finishes[0])

  const backUrl = card.is_multifaced
    ? (card.back_face_image_uri ?? null)
    : card.card_back_id
      ? buildScryfallBackUrl(card.card_back_id)
      : null

  return (
    <div className={styles.layout}>
      <div className={styles.imagePanel}>
        <FlippableCardArt
          name={card.card_name}
          w={320}
          frontUrl={card.image_large ?? null}
          backUrl={backUrl}
        />
        <div className={styles.imageFade} aria-hidden="true" />
      </div>

      <div className={styles.dataPanel}>
        <section className={styles.topRow}>
          <GameInfoCard
            cardName={card.card_name}
            setCode={card.set_code}
            setName={card.set_name}
            rarityName={card.rarity_name}
            collectorNumber={card.collector_number}
            promoTypes={card.promo_types}
            manaCost={card.mana_cost}
            typeLine={card.type_line}
            oracleText={card.oracle_text}
            artist={card.artist}
          />
          <MarketCard
            price={card.price}
            selectedFinish={selectedFinish}
            finishes={finishes}
            onFinishChange={setSelectedFinish}
            delta1d={card.price_change_1d}
            delta7d={card.price_change_7d}
            delta30d={card.price_change_30d}
          />
        </section>

        <PriceCharts card={card} finish={selectedFinish} />

        {card.legalities && Object.keys(card.legalities).length > 0 && (
          <LegalityGrid legalities={card.legalities} />
        )}

        <div className={styles.actions}>
          <Button variant="accent" style={{ flex: 1 }}>+ Add to collection</Button>
          <Button variant="ghost">Watch</Button>
          <Button variant="ghost">Set alert</Button>
        </div>
      </div>
    </div>
  )
}
