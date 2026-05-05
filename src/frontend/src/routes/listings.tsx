// src/frontend/src/routes/listings.tsx
import React, { useState, useMemo } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { Icon } from '../components/design-system/Icon'
import { ListingsTable } from '../features/ebay/components/ListingsTable'
import {
  MOCK_ACTIVE_LISTINGS,
  MOCK_SOLD_LISTINGS,
  MOCK_ATTENTION_ALERTS,
  MOCK_STRATEGY_MIX,
  formatUSD,
  priceDeltaPct,
} from '../features/ebay/mockListings'
import styles from './Listings.module.css'

export const Route = createFileRoute('/listings')({
  component: ListingsPage,
})

type Tab = 'active' | 'sold' | 'saved'

const ALERT_COLORS: Record<string, string> = {
  overpriced:  'var(--hd-red)',
  stale:       'var(--hd-amber)',
  underpriced: 'var(--hd-blue)',
}

const ALERT_ICONS: Record<string, 'arrowDown' | 'flag' | 'arrowUp'> = {
  overpriced:  'arrowDown',
  stale:       'flag',
  underpriced: 'arrowUp',
}

function ListingsPage() {
  const [tab, setTab] = useState<Tab>('active')

  // Strategy mix total for percentage
  const strategyTotal = useMemo(
    () => MOCK_STRATEGY_MIX.reduce((a, b) => a + b.count, 0) || 1,
    []
  )

  return (
    <AppShell active="listings">
      <TopBar
        title="Your listings"
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <Button variant="ghost" size="sm">
              Import
            </Button>
            <Button
              variant="accent"
              size="sm"
              icon={<Icon kind="plus" size={12} color="currentColor" />}
            >
              New listing
            </Button>
          </div>
        }
      />

      <div className={styles.page}>
        {/* ── Tabs ─────────────────────────────────── */}
        <div className={styles.tabRow} role="tablist" aria-label="Listing tabs">
          {(['active', 'sold', 'saved'] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={[styles.tab, tab === t ? styles.tabActive : ''].filter(Boolean).join(' ')}
              onClick={() => setTab(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
              {t === 'active' && (
                <span className={styles.tabCount}>{MOCK_ACTIVE_LISTINGS.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* ── Main grid ─────────────────────────────── */}
        <div className={styles.contentGrid}>
          {/* Left: table */}
          <div>
            {tab === 'active' && (
              <ListingsTable listings={MOCK_ACTIVE_LISTINGS} />
            )}
            {tab === 'sold' && (
              <div className={styles.soldTable} role="region" aria-label="Sold listings">
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Card name</th>
                      <th>Set</th>
                      <th>Condition</th>
                      <th className={styles.right}>Sale price</th>
                      <th className={styles.right}>Market at sale</th>
                      <th className={styles.right}>Days listed</th>
                      <th>Sold date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {MOCK_SOLD_LISTINGS.map((s) => {
                      const delta = priceDeltaPct(s.salePrice, s.marketPriceAtSale)
                      return (
                        <tr key={s.id} className={styles.soldRow}>
                          <td>
                            <span className={styles.soldCardName}>{s.cardName}</span>
                            {s.foil && <span className={styles.foilBadge}>foil</span>}
                          </td>
                          <td>
                            <span className={styles.setCode}>{s.setCode}</span>
                          </td>
                          <td className={styles.condition}>{s.condition}</td>
                          <td className={[styles.right, styles.mono].join(' ')}>
                            <span className={delta >= 0 ? styles.positive : styles.negative}>
                              {formatUSD(s.salePrice)}
                            </span>
                          </td>
                          <td className={[styles.right, styles.mono, styles.muted].join(' ')}>
                            {formatUSD(s.marketPriceAtSale)}
                          </td>
                          <td className={[styles.right, styles.mono, styles.muted].join(' ')}>
                            {s.daysListed}d
                          </td>
                          <td className={[styles.mono, styles.muted].join(' ')}>{s.soldDate}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {tab === 'saved' && (
              <div className={styles.emptyState}>
                <Icon kind="tag" size={32} color="var(--hd-sub)" />
                <p>No saved drafts</p>
              </div>
            )}
          </div>

          {/* Right: sidebar panels */}
          <aside className={styles.sidebar} aria-label="Listings sidebar">
            {/* Needs your attention */}
            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Needs your attention</div>
              <div className={styles.alertList}>
                {MOCK_ATTENTION_ALERTS.map((alert) => {
                  const color = ALERT_COLORS[alert.type]
                  const iconKind = ALERT_ICONS[alert.type]
                  return (
                    <div key={alert.id} className={styles.alertRow}>
                      <div
                        className={styles.alertDot}
                        style={{ background: color }}
                        aria-hidden="true"
                      />
                      <div className={styles.alertContent}>
                        <div className={styles.alertIcon} style={{ color }}>
                          <Icon kind={iconKind} size={11} color={color} />
                        </div>
                        <div>
                          <div className={styles.alertCard}>{alert.cardName}</div>
                          <div className={styles.alertMessage}>{alert.message}</div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Recent sales */}
            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Recent sales</div>
              {MOCK_SOLD_LISTINGS.slice(0, 3).map((sale) => {
                const delta = priceDeltaPct(sale.salePrice, sale.marketPriceAtSale)
                return (
                  <div key={sale.id} className={styles.recentSaleRow}>
                    <div className={styles.recentSaleName}>{sale.cardName}</div>
                    <div className={styles.recentSaleRight}>
                      <span className={styles.recentSalePrice}>{formatUSD(sale.salePrice)}</span>
                      <span
                        className={[
                          styles.recentSaleDelta,
                          delta >= 0 ? styles.positive : styles.negative,
                        ].join(' ')}
                      >
                        {delta > 0 ? '+' : ''}{delta}%
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Strategy mix */}
            <div className={styles.sidePanel}>
              <div className={styles.sidePanelTitle}>Strategy mix</div>
              <div className={styles.strategyBarWrapper}>
                <div className={styles.strategyBar} role="img" aria-label="Strategy distribution bar">
                  {MOCK_STRATEGY_MIX.map((item) => (
                    <div
                      key={item.label}
                      className={styles.strategyBarSegment}
                      style={{
                        flex: item.count,
                        background: item.color,
                      }}
                      title={`${item.label}: ${item.count}`}
                    />
                  ))}
                </div>
              </div>
              <div className={styles.strategyLegend}>
                {MOCK_STRATEGY_MIX.map((item) => (
                  <div key={item.label} className={styles.strategyLegendRow}>
                    <div
                      className={styles.strategyLegendDot}
                      style={{ background: item.color }}
                      aria-hidden="true"
                    />
                    <span className={styles.strategyLegendLabel}>{item.label}</span>
                    <span className={styles.strategyLegendCount}>
                      {item.count} ({Math.round((item.count / strategyTotal) * 100)}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
