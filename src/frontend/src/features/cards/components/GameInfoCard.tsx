// src/frontend/src/features/cards/components/GameInfoCard.tsx
import { ManaSymbol, renderSymbolsInText } from '../../../components/design-system/ManaSymbol'
import { LegalityGrid } from './LegalityGrid'
import styles from './GameInfoCard.module.css'

interface GameInfoCardProps {
  cardName: string
  setCode?: string
  setName?: string
  rarityName?: string
  collectorNumber?: string
  promoTypes?: string[]
  manaCost?: string
  typeLine?: string
  oracleText?: string
  artist?: string
  legalities?: Record<string, string>
}

function parseCostTokens(cost: string): string[] {
  return Array.from(cost.matchAll(/\{([^}]+)\}/g), (m) => m[1])
}

function rarityClass(rarity?: string): string {
  switch ((rarity ?? '').toLowerCase()) {
    case 'mythic':   return styles.rarityMythic
    case 'rare':     return styles.rarityRare
    case 'uncommon': return styles.rarityUncommon
    case 'common':
    default:         return styles.rarityCommon
  }
}

export function GameInfoCard({
  cardName,
  setCode,
  setName,
  rarityName,
  collectorNumber,
  promoTypes = [],
  manaCost,
  typeLine,
  oracleText,
  artist,
  legalities,
}: GameInfoCardProps) {
  const hasLegalities = legalities && Object.keys(legalities).length > 0
  const setCodeLower = (setCode ?? '').toLowerCase()
  const setCodeUpper = (setCode ?? '').toUpperCase()
  const rarityLower = (rarityName ?? '').toLowerCase()
  const rarityCapitalized = rarityName
    ? rarityName.charAt(0).toUpperCase() + rarityName.slice(1)
    : ''

  return (
    <div className={`${styles.card} ${rarityClass(rarityName)}`}>
      <header className={styles.setHeader}>
        <div className={styles.iconCol}>
          <i
            className={`ss ss-${setCodeLower} ss-${rarityLower}`}
            aria-hidden="true"
          />
        </div>
        <div className={styles.setText}>
          <div className={styles.setLine}>
            {setName && <span className={styles.setName}>{setName}</span>}
            {setCode && <span className={styles.setCode}>({setCodeUpper})</span>}
          </div>
          <div className={styles.metaLine}>
            {rarityCapitalized && (
              <span className={styles.rarity}>{rarityCapitalized}</span>
            )}
            {collectorNumber && (
              <>
                <span className={styles.metaSep}>·</span>
                <span>#{collectorNumber}</span>
              </>
            )}
            {promoTypes.length > 0 && (
              <span className={styles.badges}>
                {promoTypes.map((pt) => (
                  <span key={pt} className={styles.badge}>✦ {pt}</span>
                ))}
              </span>
            )}
          </div>
        </div>
      </header>

      <div className={styles.titleRow}>
        <h1 className={styles.name}>{cardName}</h1>
        {manaCost && (
          <div className={styles.manaRow}>
            {parseCostTokens(manaCost).map((tok, i) => (
              <ManaSymbol key={i} symbol={tok} size={14} cost />
            ))}
          </div>
        )}
      </div>

      {typeLine && <div className={styles.typeLine}>{typeLine}</div>}

      {oracleText && (
        <div className={styles.oracleText}>
          {oracleText.split('\n').map((line, i) => (
            <p key={i}>{renderSymbolsInText(line, { size: 11 })}</p>
          ))}
        </div>
      )}

      {hasLegalities && (
        <div className={styles.legalitySection}>
          <div className={styles.sectionLabel}>Legalities</div>
          <LegalityGrid legalities={legalities!} />
        </div>
      )}

      {artist && (
        <footer className={styles.footer}>Illus. {artist}</footer>
      )}
    </div>
  )
}
