import { useState, useMemo } from 'react'
import { Link } from '@tanstack/react-router'
import { AIBadge } from '../../../components/design-system/AIBadge'
import { Icon } from '../../../components/design-system/Icon'
import type { EbayLiveListing } from '../mockListings'
import styles from './ListingsTable.module.css'

interface ListingsTableProps {
  listings: EbayLiveListing[]
  isLoading?: boolean
  selectedId?: string
  onRowClick?: (id: string) => void
}

type SortKey = 'cardName' | 'setCode' | 'appName' | 'conditionLabel' | 'finish' | 'style' | 'price' | 'daysListed' | 'watchCount'
type SortDir = 'asc' | 'desc'

const APP_PALETTE = ['#a78bfa', '#60a5fa', '#34d399', '#f59e0b']
const COL_COUNT = 10

function SortIndicator({ active, dir }: { active: boolean; dir: SortDir }) {
  return (
    <span className={active ? styles.sortIndicatorActive : styles.sortIndicator}>
      {active ? (dir === 'asc' ? '▲' : '▼') : '⇅'}
    </span>
  )
}

export function ListingsTable({ listings, isLoading = false, selectedId, onRowClick }: ListingsTableProps) {
  const [filter, setFilter] = useState('')
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const appColors = useMemo<Record<string, string>>(() => {
    const codes = [...new Set(listings.map((l) => l.appCode))]
    return Object.fromEntries(codes.map((code, i) => [code, APP_PALETTE[i % APP_PALETTE.length]]))
  }, [listings])

  const visible = useMemo(() => {
    const filtered = filter.trim()
      ? listings.filter((l) => l.cardName.toLowerCase().includes(filter.toLowerCase()))
      : listings

    if (!sortKey) return filtered

    return [...filtered].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av
      }
      const as = String(av ?? '').toLowerCase()
      const bs = String(bv ?? '').toLowerCase()
      if (as < bs) return sortDir === 'asc' ? -1 : 1
      if (as > bs) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [listings, filter, sortKey, sortDir])

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
          <colgroup>
            <col className={styles.colName} />
            <col className={styles.colSet} />
            <col className={styles.colApp} />
            <col className={styles.colCond} />
            <col className={styles.colFinish} />
            <col className={styles.colStyle} />
            <col className={styles.colPrice} />
            <col className={styles.colDays} />
            <col className={styles.colWatchers} />
            <col className={styles.colStatus} />
          </colgroup>
          <thead className={styles.thead}>
            <tr>
              <th scope="col" className={styles.sortable} onClick={() => handleSort('cardName')}>
                CARD NAME <SortIndicator active={sortKey === 'cardName'} dir={sortDir} />
              </th>
              <th scope="col" className={styles.sortable} onClick={() => handleSort('setCode')}>
                SET <SortIndicator active={sortKey === 'setCode'} dir={sortDir} />
              </th>
              <th scope="col" className={styles.sortable} onClick={() => handleSort('appName')}>
                APP <SortIndicator active={sortKey === 'appName'} dir={sortDir} />
              </th>
              <th scope="col" className={styles.sortable} onClick={() => handleSort('conditionLabel')}>
                COND <SortIndicator active={sortKey === 'conditionLabel'} dir={sortDir} />
              </th>
              <th scope="col" className={styles.sortable} onClick={() => handleSort('finish')}>
                FINISH <SortIndicator active={sortKey === 'finish'} dir={sortDir} />
              </th>
              <th scope="col" className={styles.sortable} onClick={() => handleSort('style')}>
                STYLE <SortIndicator active={sortKey === 'style'} dir={sortDir} />
              </th>
              <th scope="col" className={[styles.right, styles.sortable].join(' ')} onClick={() => handleSort('price')}>
                PRICE <SortIndicator active={sortKey === 'price'} dir={sortDir} />
              </th>
              <th scope="col" className={[styles.center, styles.sortable].join(' ')} onClick={() => handleSort('daysListed')}>
                DAYS <SortIndicator active={sortKey === 'daysListed'} dir={sortDir} />
              </th>
              <th scope="col" className={[styles.center, styles.sortable].join(' ')} onClick={() => handleSort('watchCount')}>
                WATCH <SortIndicator active={sortKey === 'watchCount'} dir={sortDir} />
              </th>
              <th scope="col" className={styles.center}>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <>
                {[0, 1, 2].map((i) => (
                  <tr key={i} data-testid="skeleton-row" className={styles.skeletonRow}>
                    <td><div className={styles.skeletonText} style={{ width: '75%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '60%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '80%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '60%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '60%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '60%' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '70%', marginLeft: 'auto' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '50%', margin: '0 auto' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '40%', margin: '0 auto' }} /></td>
                    <td><div className={styles.skeletonText} style={{ width: '50%', margin: '0 auto' }} /></td>
                  </tr>
                ))}
              </>
            )}
            {!isLoading && visible.length === 0 && (
              <tr>
                <td colSpan={COL_COUNT} className={styles.empty}>No listings found</td>
              </tr>
            )}
            {!isLoading && visible.map((listing) => {
              const appColor = appColors[listing.appCode] ?? APP_PALETTE[0]
              return (
                <tr
                  key={listing.itemId}
                  className={[
                    styles.row,
                    listing.itemId === selectedId ? styles.rowSelected : '',
                  ].filter(Boolean).join(' ')}
                  onClick={() => onRowClick?.(listing.itemId)}
                  style={{ cursor: onRowClick ? 'pointer' : 'default' }}
                >
                  {/* Card name + thumbnail */}
                  <td>
                    <div className={styles.nameCell}>
                      {listing.imageUrl && (
                        <img
                          src={listing.imageUrl}
                          alt=""
                          className={styles.thumbnail}
                          loading="lazy"
                        />
                      )}
                      <div className={styles.nameText}>
                        {onRowClick ? (
                          <span className={styles.cardName}>{listing.cardName}</span>
                        ) : (
                          <Link
                            to="/listings_/$id"
                            params={{ id: listing.itemId }}
                            className={styles.cardName}
                          >
                            {listing.cardName}
                          </Link>
                        )}
                        <a
                          href={listing.viewItemUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={styles.ebayLink}
                          title="View on eBay"
                          onClick={(e) => e.stopPropagation()}
                        >
                          eBay ↗
                        </a>
                      </div>
                    </div>
                  </td>

                  {/* Set code */}
                  <td>
                    <span className={styles.setChip}>{listing.setCode || '—'}</span>
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
                      {listing.appName || listing.appCode}
                    </span>
                  </td>

                  {/* Condition */}
                  <td>
                    <span className={styles.chip}>{listing.conditionLabel || '—'}</span>
                  </td>

                  {/* Finish */}
                  <td>
                    <span className={listing.finish === 'Regular' || !listing.finish ? styles.chip : styles.chipAccent}>
                      {listing.finish || '—'}
                    </span>
                  </td>

                  {/* Style / frame */}
                  <td>
                    <span className={styles.chip}>{listing.style || '—'}</span>
                  </td>

                  {/* Price */}
                  <td className={styles.right}>
                    <span className={styles.price}>
                      {listing.price > 0 ? `$${listing.price.toFixed(2)}` : '—'}
                    </span>
                  </td>

                  {/* Days listed */}
                  <td className={styles.center}>
                    <span className={styles.days}>
                      {listing.daysListed > 0 ? `${listing.daysListed}d` : '—'}
                    </span>
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
