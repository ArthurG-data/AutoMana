// src/frontend/src/features/ebay/components/ListingDetailPanel.tsx
import { useState, useEffect } from 'react'
import { Icon } from '../../../components/design-system/Icon'
import type { EbayLiveListing } from '../mockListings'
import { fetchRecommendation, stageAction, type ListingRecommendation } from '../api'
import { SignalBadge } from './SignalBadge'
import styles from './ListingDetailPanel.module.css'

interface ListingDetailPanelProps {
  listing: EbayLiveListing
  onEdit: () => void
  onClose: () => void
  onCompare: () => void
}

export function ListingDetailPanel({ listing, onEdit, onClose, onCompare }: ListingDetailPanelProps) {
  const [recommendation, setRecommendation] = useState<ListingRecommendation | null>(null)
  const [recLoading, setRecLoading] = useState(false)
  const [recError, setRecError] = useState<string | null>(null)
  const [staged, setStaged] = useState(false)
  const [staging, setStaging] = useState(false)
  const [stageError, setStageError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setRecommendation(null)
    setRecError(null)
    setStaged(false)
    setStageError(null)
    setRecLoading(true)

    fetchRecommendation(listing.appCode, listing)
      .then((rec) => {
        if (!cancelled) {
          setRecommendation(rec)
          setRecLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRecError('Unable to load recommendation')
          setRecLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [listing.itemId, listing.appCode])

  async function handleStage() {
    if (!recommendation) return
    setStaging(true)
    setStageError(null)
    try {
      await stageAction(listing.appCode, listing.itemId, {
        action_type: recommendation.suggested_action,
        strategy_kind: recommendation.strategy_kind,
        suggested_price: recommendation.suggested_price,
      })
      setStaged(true)
    } catch (err) {
      setStageError(err instanceof Error ? err.message : 'Failed to stage action')
    } finally {
      setStaging(false)
    }
  }

  const stageDisabled =
    recLoading ||
    !recommendation ||
    recommendation.suggested_action === 'hold' ||
    staged ||
    staging

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>{listing.cardName}</span>
        <button onClick={onClose} className={styles.closeBtn} aria-label="Close panel">
          <Icon kind="close" size={14} color="currentColor" />
        </button>
      </div>

      {listing.imageUrl ? (
        <img src={listing.imageUrl} alt={listing.cardName} className={styles.image} />
      ) : (
        <div className={styles.imagePlaceholder}>
          <span className={styles.placeholderSet}>{listing.setCode}</span>
        </div>
      )}

      <div className={styles.fields}>
        {[
          { label: 'Set', value: listing.setCode || '—' },
          { label: 'Condition', value: listing.conditionLabel || '—' },
          { label: 'Days listed', value: listing.daysListed > 0 ? `${listing.daysListed}d` : '—' },
          { label: 'App', value: listing.appName || listing.appCode },
        ].map(({ label, value }) => (
          <div key={label} className={styles.row}>
            <span className={styles.label}>{label}</span>
            <span className={styles.value}>{value}</span>
          </div>
        ))}
        <div className={styles.row}>
          <span className={styles.label}>Price</span>
          <span className={styles.valueAccent}>
            {listing.currency} {listing.price.toFixed(2)}
          </span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>Watchers</span>
          <span className={styles.value}>{listing.watchCount}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>eBay</span>
          <a
            href={listing.viewItemUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.link}
          >
            View ↗
          </a>
        </div>
      </div>

      {/* ── Strategy Advisor ─────────────────────────────────────── */}
      <div className={styles.advisor}>
        <span className={styles.advisorHeading}>Strategy Advisor</span>

        {recLoading && (
          <span className={styles.advisorMeta}>Loading recommendation...</span>
        )}

        {recError && !recLoading && (
          <span className={styles.advisorError}>{recError}</span>
        )}

        {recommendation && !recLoading && (
          <>
            <div className={styles.advisorSignal}>
              <SignalBadge
                action={recommendation.suggested_action}
                confidence={recommendation.confidence}
                currency={listing.currency}
              />
            </div>

            {Object.keys(recommendation.all_strategies).length > 0 && (
              <ul className={styles.strategyList}>
                {Object.entries(recommendation.all_strategies).map(([kind, strategy]) => {
                  const isSelected = kind === recommendation.strategy_kind
                  return (
                    <li
                      key={kind}
                      className={[styles.strategyItem, isSelected ? styles.strategyItemActive : ''].filter(Boolean).join(' ')}
                    >
                      <span className={[styles.strategyKind, isSelected ? styles.strategyKindActive : ''].filter(Boolean).join(' ')}>
                        {isSelected ? '▶ ' : '  '}{kind}
                      </span>
                      <span className={styles.strategyPrice}>
                        {listing.currency} {strategy.price.toFixed(2)}
                      </span>
                      <span className={styles.strategyConfidence}>
                        {Math.round(strategy.confidence * 100)}%
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}

            {stageError && (
              <span className={styles.advisorError}>{stageError}</span>
            )}

            {staged && (
              <span className={styles.advisorSuccess}>Action queued ✓</span>
            )}

            <button
              className={styles.stageBtn}
              onClick={handleStage}
              disabled={stageDisabled}
            >
              {staged ? 'Action queued ✓' : 'Stage Action'}
            </button>
          </>
        )}
      </div>

      <div className={styles.actions}>
        <button onClick={onCompare} className={styles.compareBtn}>
          Compare market
        </button>
        <button onClick={onEdit} className={styles.editBtn}>
          Edit listing
        </button>
      </div>
    </div>
  )
}
