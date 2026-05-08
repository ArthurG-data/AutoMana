import { useState, useMemo } from 'react'
import { AIBadge } from '../../../components/design-system/AIBadge'
import { Icon } from '../../../components/design-system/Icon'
import type { EbayLiveListing } from '../mockListings'
import styles from './ListingsTable.module.css'

interface ListingsTableProps {
  listings: EbayLiveListing[]
  isLoading?: boolean
}

const APP_PALETTE = ['#a78bfa', '#60a5fa', '#34d399', '#f59e0b']

export function ListingsTable({ listings, isLoading = false }: ListingsTableProps) {
  const [filter, setFilter] = useState('')

  const appColors = useMemo<Record<string, string>>(() => {
    const codes = [...new Set(listings.map((l) => l.appCode))]
    return Object.fromEntries(codes.map((code, i) => [code, APP_PALETTE[i % APP_PALETTE.length]]))
  }, [listings])

  const visible = useMemo(
    () =>
      filter.trim()
        ? listings.filter((l) => l.cardName.toLowerCase().includes(filter.toLowerCase()))
        : listings,
    [listings, filter]
  )

  const appCount = useMemo(
    () => new Set(listings.map((l) => l.appCode)).size,
    [listings]
  )

  return (
    <div className={styles.wrapper}>
      {/* ── Filter bar ──────────────────────────────────────────── */}
      <div className={styles.filterBar}>
        <div className={styles.filterInputWrap}>
          <Icon kind="search" size={12} color="#444" />
          <input
            className={styles.filterInput}
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by card name…"
            aria-label="Filter by card name"
          />
        </div>
        {!isLoading && (
          <span className={styles.filterMeta}>
            {listings.length} listings · {appCount} app{appCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* ── Table ───────────────────────────────────────────────── */}
      <div className={styles.tableWrap} role="region" aria-label="Listings table">
        <table className={styles.table}>
          <thead className={styles.thead}>
            <tr>
              <th scope="col">CARD NAME</th>
              <th scope="col">APP</th>
              <th scope="col">COND</th>
              <th scope="col" className={styles.right}>PRICE</th>
              <th scope="col" className={styles.center}>WATCHERS</th>
              <th scope="col" className={styles.center}>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <>
                {[0, 1, 2].map((i) => (
                  <tr key={i} data-testid="skeleton-row" className={styles.skeletonRow}>
                    <td><div className={styles.skeletonText} style={{ width: '60%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '70%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '40%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '50%', marginLeft: 'auto' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '30%', margin: '0 auto' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '50%', margin: '0 auto' }} /></td>
                  </tr>
                ))}
              </>
            )}
            {!isLoading && visible.length === 0 && (
              <tr>
                <td colSpan={6} className={styles.empty}>No listings found</td>
              </tr>
            )}
            {!isLoading && visible.map((listing) => {
              const appColor = appColors[listing.appCode] ?? APP_PALETTE[0]
              const badge = [listing.conditionLabel, listing.setInfo].filter(Boolean).join(' · ')
              return (
                <tr key={listing.itemId} className={styles.row}>
                  {/* Card name + COND · SET badge */}
                  <td>
                    <div className={styles.nameCell}>
                      <a
                        href={listing.viewItemUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.cardName}
                      >
                        {listing.cardName}
                      </a>
                      {badge && <span className={styles.nameBadge}>{badge}</span>}
                    </div>
                  </td>

                  {/* App */}
                  <td>
                    <span
                      className={styles.appBadge}
                      style={{
                        color: appColor,
                        background: `${appColor}1a`,
                        border: `1px solid ${appColor}44`,
                      }}
                    >
                      {listing.appName}
                    </span>
                  </td>

                  {/* Condition */}
                  <td>
                    <span className={styles.cond}>{listing.conditionLabel}</span>
                  </td>

                  {/* Price */}
                  <td className={styles.right}>
                    <span className={styles.price}>${listing.price.toFixed(2)}</span>
                  </td>

                  {/* Watchers */}
                  <td className={styles.center}>
                    <span className={styles.watchers}>
                      <Icon kind="eye" size={11} color="#555" />
                      {listing.watchCount}
                    </span>
                  </td>

                  {/* Status */}
                  <td className={styles.center}>
                    <AIBadge status="ok" showLabel size="sm" />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
