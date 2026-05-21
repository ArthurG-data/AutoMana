// src/frontend/src/features/cards/components/GameInfoCard.tsx
import { useNavigate } from '@tanstack/react-router'
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

const PROMO_NAMES: Record<string, string> = {
  boosterfun: 'Booster Fun',
  extendedart: 'Extended Art',
  showcase: 'Showcase',
  borderless: 'Borderless',
  buyabox: 'Buy-a-Box',
  prerelease: 'Prerelease',
  gameday: 'Game Day',
  promo: 'Promo',
  etched: 'Etched',
  fullart: 'Full Art',
  intropack: 'Intro Pack',
  starterdeck: 'Starter Deck',
  bundle: 'Bundle',
  giftbox: 'Gift Box',
  judgegift: 'Judge Gift',
  jpwalker: 'JP Planeswalker',
  planeswalkerstamped: 'Planeswalker Stamped',
  promostamped: 'Promo Stamped',
  textured: 'Textured',
  glossy: 'Glossy',
  thick: 'Thick Stock',
  gilded: 'Gilded',
  galaxyfoil: 'Galaxy Foil',
  surgefoil: 'Surge Foil',
  raisedfoil: 'Raised Foil',
  neonink: 'Neon Ink',
  confettifoil: 'Confetti Foil',
  halofoil: 'Halofoil',
  oilslick: 'Oil Slick',
  doublerainbow: 'Double Rainbow',
  godzillaseries: 'Godzilla',
  draculaseries: 'Dracula',
  ampersand: 'Ampersand',
  scroll: 'Scroll',
  ravnicacity: 'Ravnica City',
  serialized: 'Serialized',
  stepandcompleat: 'Compleated',
}

function formatPromoType(p: string): string {
  const key = p.toLowerCase().replace(/[-_\s]/g, '')
  if (PROMO_NAMES[key]) return PROMO_NAMES[key]
  return p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()
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
  const navigate = useNavigate()
  const hasLegalities = legalities && Object.keys(legalities).length > 0
  const setCodeLower = (setCode ?? '').toLowerCase()
  const setCodeUpper = (setCode ?? '').toUpperCase()
  const rarityLower = (rarityName ?? '').toLowerCase()
  const rarityCapitalized = rarityName
    ? rarityName.charAt(0).toUpperCase() + rarityName.slice(1)
    : ''
  const goToSetSearch = () => {
    if (setCode) navigate({ to: '/search', search: { set: setCode } })
  }
  const goToArtistSearch = () => {
    if (artist) navigate({ to: '/search', search: { artist } })
  }

  return (
    <div className={`${styles.card} ${rarityClass(rarityName)}`}>
      <header className={styles.setHeader}>
        <button
          type="button"
          className={styles.iconCol}
          onClick={goToSetSearch}
          disabled={!setCode}
          aria-label={setCode ? `Search ${setCodeUpper}` : 'Set icon'}
          title={setCode ? `Search ${setCodeUpper}` : undefined}
        >
          <i
            className={`ss ss-${setCodeLower} ss-${rarityLower}`}
            aria-hidden="true"
          />
        </button>
        <div className={styles.setText}>
          {(setName || setCode) ? (
            <button
              type="button"
              className={styles.setLink}
              onClick={goToSetSearch}
              disabled={!setCode}
              title={setCode ? `Search ${setCodeUpper}` : undefined}
            >
              {setName && <span className={styles.setName}>{setName}</span>}
              {setCode && <span className={styles.setCode}>({setCodeUpper})</span>}
            </button>
          ) : (
            <div className={styles.setLine} />
          )}
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
          </div>
          {promoTypes.length > 0 && (
            <div className={styles.promoRow}>
              {promoTypes.map((pt) => (
                <span key={pt} className={styles.promoBadge} title={pt}>
                  ✦ {formatPromoType(pt)}
                </span>
              ))}
            </div>
          )}
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
        <footer className={styles.footer}>
          Illus.{' '}
          <button
            type="button"
            className={styles.artistLink}
            onClick={goToArtistSearch}
            title={`Search cards illustrated by ${artist}`}
          >
            {artist}
          </button>
        </footer>
      )}
    </div>
  )
}
