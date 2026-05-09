// src/frontend/src/routes/listing.$id.tsx
import { useState } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { PriceBand } from '../components/design-system/PriceBand'
import {
  StrategyCard,
  buildStrategies,
  type StrategyKind,
} from '../features/ebay/components/StrategyCard'
import { formatUSD, feeEstimate } from '../features/ebay/mockListings'
import { useListingsStore } from '../store/listings'
import styles from './ListingDetail.module.css'

export const Route = createFileRoute('/listings_/$id')({
  component: ListingDetailPage,
})

function ListingDetailPage() {
  const { id } = Route.useParams()
  const listing = useListingsStore((s) => s.getById(id))
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyKind>('balanced')

  if (!listing) {
    return (
      <AppShell active="listings">
        <TopBar title="Listing not found" breadcrumb="LISTINGS › NOT FOUND" />
        <div className={styles.notFound}>
          <p>
            Listing <code>{id}</code> was not found.{' '}
            Listings are loaded when you visit the listings page.
          </p>
          <Link to="/listings" className={styles.backLink}>
            ← Back to listings
          </Link>
        </div>
      </AppShell>
    )
  }

  // Use the listing price as market price proxy until MTGStock data is synced.
  const marketPrice = listing.price || 0
  const strategies = buildStrategies(marketPrice)
  const active = strategies.find((s) => s.kind === selectedStrategy) ?? strategies[1]
  const midPct = (active.pctRange[0] + active.pctRange[1]) / 2
  const recommendedPrice = marketPrice * (1 + midPct / 100)
  const payout = feeEstimate(recommendedPrice)

  const displaySet = listing.setCode || '—'
  const displayName = listing.cardName

  return (
    <AppShell active="listings">
      <TopBar
        title={displayName}
        breadcrumb={`LISTINGS › ${displaySet} › ${displayName.toUpperCase()}`}
      />

      <div className={styles.page}>
        <div className={styles.threeCol}>
          {/* LEFT: card image + info panel */}
          <aside className={styles.cardPanel} aria-label="Card details">
            {listing.imageUrl ? (
              <img
                src={listing.imageUrl}
                alt={displayName}
                className={styles.cardImage}
              />
            ) : (
              <div className={styles.cardArtPlaceholder} aria-label={displayName}>
                <div className={styles.cardArtInner}>
                  <span className={styles.cardArtName}>{displayName}</span>
                  <span className={styles.cardArtSet}>{displaySet}</span>
                </div>
              </div>
            )}

            <div className={styles.cardInfo}>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>eBay ID</span>
                <span className={styles.infoValue}>{listing.itemId}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Set</span>
                <span className={styles.infoValue}>{displaySet}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Condition</span>
                <span className={styles.infoValue}>{listing.conditionLabel || '—'}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Finish</span>
                <span className={styles.infoValue}>{listing.finish}</span>
              </div>
              {listing.style && (
                <div className={styles.cardInfoRow}>
                  <span className={styles.infoLabel}>Style</span>
                  <span className={styles.infoValue}>{listing.style}</span>
                </div>
              )}
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Days listed</span>
                <span className={styles.infoValue}>
                  {listing.daysListed > 0 ? `${listing.daysListed}d` : '—'}
                </span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Watchers</span>
                <span className={styles.infoValue}>{listing.watchCount}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Listed at</span>
                <span className={styles.infoValueAccent}>
                  {listing.price > 0
                    ? `${listing.currency} ${listing.price.toFixed(2)}`
                    : '—'}
                </span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>App</span>
                <span className={styles.infoValue}>{listing.appName || listing.appCode}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>eBay listing</span>
                <a
                  href={listing.viewItemUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.ebayLink}
                >
                  View ↗
                </a>
              </div>
            </div>
          </aside>

          {/* CENTER: strategy advisor */}
          <section className={styles.strategySection} aria-label="Strategy advisor">
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Strategy advisor</h2>
              <p className={styles.sectionSub}>
                Listed at{' '}
                <strong>
                  {listing.currency} {listing.price.toFixed(2)}
                </strong>{' '}
                — connect MTGStock to see market price
              </p>
            </div>

            <div className={styles.strategyList}>
              {strategies.map((strategy) => (
                <StrategyCard
                  key={strategy.kind}
                  strategy={strategy}
                  selected={selectedStrategy === strategy.kind}
                  onSelect={setSelectedStrategy}
                />
              ))}
            </div>

            <div className={styles.bandSection}>
              <div className={styles.bandLabel}>Price band (estimated)</div>
              <PriceBand
                low={marketPrice * 0.8}
                p25={marketPrice * 0.9}
                market={marketPrice}
                p75={marketPrice * 1.1}
                high={marketPrice * 1.2}
                listed={recommendedPrice}
              />
              <div className={styles.bandLegend}>
                <span className={styles.bandLegendItem}>
                  <span className={styles.bandLegendDotLow} /> −20%
                </span>
                <span className={styles.bandLegendItem}>
                  <span className={styles.bandLegendDotMid} /> Listed
                </span>
                <span className={styles.bandLegendItem}>
                  <span className={styles.bandLegendDotHigh} /> +20%
                </span>
              </div>
            </div>
          </section>

          {/* RIGHT: payout projection */}
          <aside className={styles.payoutPanel} aria-label="Payout projection">
            <div className={styles.sidePanelTitle}>Payout projection</div>

            <div className={styles.payoutItem}>
              <span className={styles.payoutLabel}>Strategy</span>
              <span className={styles.payoutValue}>{active.name}</span>
            </div>
            <div className={styles.payoutItem}>
              <span className={styles.payoutLabel}>Recommended price</span>
              <span className={styles.payoutValue}>{formatUSD(recommendedPrice)}</span>
            </div>
            <div className={styles.payoutItem}>
              <span className={styles.payoutLabel}>Est. days to sell</span>
              <span className={styles.payoutValue}>{active.daysRange}</span>
            </div>

            <div className={styles.payoutDivider} />

            <div className={styles.payoutItem}>
              <span className={styles.payoutLabel}>Gross sale</span>
              <span className={styles.payoutValue}>{formatUSD(recommendedPrice)}</span>
            </div>
            <div className={styles.payoutItem}>
              <span className={styles.payoutLabel}>eBay fees (~13.25%)</span>
              <span className={styles.payoutValueNeg}>
                −{formatUSD(recommendedPrice - payout)}
              </span>
            </div>
            <div className={styles.payoutItem}>
              <span className={styles.payoutLabel}>Net payout</span>
              <span className={styles.payoutValueHighlight}>{formatUSD(payout)}</span>
            </div>

            <div className={styles.payoutActions}>
              <button className={styles.applyBtn}>Apply strategy</button>
              <Link to="/listings" className={styles.cancelLink}>
                ← All listings
              </Link>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
