// src/frontend/src/features/cards/components/CardDetailView.tsx
import { useState } from 'react'
import { FlippableCardArt } from '../../../components/design-system/FlippableCardArt'
import { buildScryfallBackUrl } from '../utils/scryfallBackUrl'
import { Button } from '../../../components/ui/Button'
import { PriceCharts } from './PriceCharts'
import { GameInfoCard } from './GameInfoCard'
import { MarketCard } from './MarketCard'
import { AIAnalyticsCard } from './AIAnalyticsCard'
import { VersionsTable } from './VersionsTable'
import { OtherSetsTable } from './OtherSetsTable'
import type { CardDetail, CardVersionRow, OtherSetRow } from '../types'
import styles from './CardDetailView.module.css'

interface CardDetailViewProps {
  card: CardDetail
  versionsInSet?: CardVersionRow[]
  otherSets?: OtherSetRow[]
}

export function CardDetailView({ card, versionsInSet, otherSets }: CardDetailViewProps) {
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
          finish={selectedFinish}
        />
        <div className={styles.actions}>
          <Button variant="accent" style={{ width: '100%', justifyContent: 'center' }}>+ Add to collection</Button>
          <div className={styles.secondaryActions}>
            <Button variant="ghost" style={{ justifyContent: 'center' }}>Watch</Button>
            <Button variant="ghost" style={{ justifyContent: 'center' }}>Set alert</Button>
          </div>
        </div>
        <div className={styles.imageFade} aria-hidden="true" />
      </div>

      <div className={styles.dataPanel}>
        <section className={styles.topGrid}>
          <div className={styles.gameInfoSlot}>
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
              legalities={card.legalities}
            />
          </div>
          <div className={styles.marketSlot}>
            <MarketCard
              price={card.price}
              selectedFinish={selectedFinish}
              finishes={finishes}
              onFinishChange={setSelectedFinish}
              delta1d={card.price_change_1d}
              delta7d={card.price_change_7d}
              delta30d={card.price_change_30d}
            />
          </div>
          <div className={styles.aiSlot}>
            <AIAnalyticsCard />
          </div>
          <div className={styles.chartSlot}>
            <PriceCharts card={card} finish={selectedFinish} />
          </div>
        </section>

        {versionsInSet && versionsInSet.length > 0 && (
          <VersionsTable
            versions={versionsInSet}
            currentVersionId={card.card_version_id.toString()}
            setCode={card.set_code}
          />
        )}

        {otherSets && otherSets.length > 0 && (
          <OtherSetsTable
            sets={otherSets}
            currentVersionId={card.card_version_id.toString()}
          />
        )}
      </div>
    </div>
  )
}
