// src/frontend/src/routes/listing.$id.tsx
import { useState } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { PriceBand } from '../components/design-system/PriceBand'
import { AIBadge } from '../components/design-system/AIBadge'
import {
  StrategyCard,
  buildStrategies,
  type StrategyKind,
} from '../features/ebay/components/StrategyCard'
import {
  MOCK_ACTIVE_LISTINGS,
  formatUSD,
  feeEstimate,
} from '../features/ebay/mockListings'
import styles from './ListingDetail.module.css'

export const Route = createFileRoute('/listings_/$id')({
  component: ListingDetailPage,
})

function ListingDetailPage() {
  const { id } = Route.useParams()
  const listing = MOCK_ACTIVE_LISTINGS.find((l) => l.id === id)
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyKind>('balanced')

  if (!listing) {
    return (
      <AppShell active="listings">
        <TopBar title="Listing not found" breadcrumb="LISTINGS › NOT FOUND" />
        <div className={styles.notFound}>
          <p>Listing <code>{id}</code> was not found.</p>
          <Link to="/listings" className={styles.backLink}>
            ← Back to listings
          </Link>
        </div>
      </AppShell>
    )
  }

  const strategies = buildStrategies(listing.marketPrice)
  const active = strategies.find((s) => s.kind === selectedStrategy) ?? strategies[1]

  // Mid recommended price for selected strategy
  const midPct = (active.pctRange[0] + active.pctRange[1]) / 2
  const recommendedPrice = listing.marketPrice * (1 + midPct / 100)
  const payout = feeEstimate(recommendedPrice)
  const pl = payout - listing.costBasis

  return (
    <AppShell active="listings">
      <TopBar
        title={listing.cardName}
        breadcrumb={`LISTINGS › ${listing.setCode.toUpperCase()} › ${listing.cardName.toUpperCase()}`}
      />

      <div className={styles.page}>
        {/* ── Three-column layout ───────────────────── */}
        <div className={styles.threeCol}>
          {/* LEFT: card art + info panel */}
          <aside className={styles.cardPanel} aria-label="Card details">
            <div className={styles.cardArtPlaceholder} aria-label={listing.cardName}>
              <div className={styles.cardArtInner}>
                <span className={styles.cardArtName}>{listing.cardName}</span>
                <span className={styles.cardArtSet}>{listing.setCode}</span>
              </div>
            </div>

            <div className={styles.cardInfo}>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Listing ID</span>
                <span className={styles.infoValue}>{listing.id.toUpperCase()}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Days listed</span>
                <span className={styles.infoValue}>{listing.daysListed}d</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Views</span>
                <span className={styles.infoValue}>{listing.views}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Watchers</span>
                <span className={styles.infoValue}>{listing.watchers}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Condition</span>
                <span className={styles.infoValue}>{listing.condition}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Cost basis</span>
                <span className={styles.infoValue}>{formatUSD(listing.costBasis)}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>Listed at</span>
                <span className={styles.infoValueAccent}>{formatUSD(listing.listedPrice)}</span>
              </div>
              <div className={styles.cardInfoRow}>
                <span className={styles.infoLabel}>AI status</span>
                <AIBadge status={listing.aiStatus} showLabel size="sm" />
              </div>
            </div>
          </aside>

          {/* CENTER: strategy advisor */}
          <section className={styles.strategySection} aria-label="Strategy advisor">
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Strategy advisor</h2>
              <p className={styles.sectionSub}>
                Market at <strong>{formatUSD(listing.marketPrice)}</strong> — select a strategy
              </p>
            </div>

            {/* Strategy cards */}
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

            {/* Market band visualization */}
            <div className={styles.bandSection}>
              <div className={styles.bandLabel}>Market price band</div>
              <PriceBand
                low={listing.marketBand.low}
                p25={listing.marketBand.p25}
                market={listing.marketBand.median}
                p75={listing.marketBand.p75}
                high={listing.marketBand.high}
                listed={recommendedPrice}
              />
              <div className={styles.bandLegend}>
                <span className={styles.bandLegendItem}>
                  <span className={styles.bandLegendDotLow} /> Low: {formatUSD(listing.marketBand.low)}
                </span>
                <span className={styles.bandLegendItem}>
                  <span className={styles.bandLegendDotMid} /> Median: {formatUSD(listing.marketBand.median)}
                </span>
                <span className={styles.bandLegendItem}>
                  <span className={styles.bandLegendDotHigh} /> High: {formatUSD(listing.marketBand.high)}
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

            <div className={styles.payoutDivider} />

            <div className={styles.payoutItem}>
              <span className={styles.payoutLabel}>Cost basis</span>
              <span className={styles.payoutValue}>{formatUSD(listing.costBasis)}</span>
            </div>
            <div className={styles.payoutItem}>
              <span className={styles.payoutLabel}>Profit / Loss</span>
              <span className={pl >= 0 ? styles.payoutPL : styles.payoutPLNeg}>
                {pl >= 0 ? '+' : ''}{formatUSD(pl)}
              </span>
            </div>

            <div className={styles.payoutActions}>
              <button className={styles.applyBtn}>
                Apply strategy
              </button>
              <Link to="/listings" className={styles.cancelLink}>
                Cancel
              </Link>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
