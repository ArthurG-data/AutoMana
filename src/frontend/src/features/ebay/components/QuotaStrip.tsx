// src/frontend/src/features/ebay/components/QuotaStrip.tsx
import React from 'react'
import { Icon } from '../../../components/design-system/Icon'
import { MOCK_QUOTA_BY_USER, DAILY_QUOTA_LIMIT } from '../mockAuthorizedUsers'
import styles from './QuotaStrip.module.css'

export function QuotaStrip() {
  const totalUsed = MOCK_QUOTA_BY_USER.reduce((a, u) => a + u.calls, 0)
  const pct = Math.round((totalUsed / DAILY_QUOTA_LIMIT) * 100)

  return (
    <div className={styles.quotaStrip}>
      <div className={styles.quotaHeader}>
        <div className={styles.quotaTitle}>
          <Icon kind="chart" size={14} color="var(--hd-muted)" />
          Daily API quota
        </div>
        <div className={styles.quotaNumbers}>
          <span className={styles.quotaUsed}>{totalUsed.toLocaleString()}</span>
          <span className={styles.quotaOf}> / {DAILY_QUOTA_LIMIT.toLocaleString()} calls</span>
          <span className={styles.quotaPct}>{pct}%</span>
        </div>
      </div>

      <div
        className={styles.quotaBar}
        role="img"
        aria-label={`Quota usage: ${totalUsed} of ${DAILY_QUOTA_LIMIT} calls`}
      >
        {MOCK_QUOTA_BY_USER.map((u) => (
          <div
            key={u.userId}
            className={styles.quotaSegment}
            style={{
              flex: u.calls,
              background: u.color,
            }}
            title={`${u.name}: ${u.calls} calls`}
          />
        ))}
        <div
          className={styles.quotaSegmentEmpty}
          style={{ flex: Math.max(DAILY_QUOTA_LIMIT - totalUsed, 0) }}
        />
      </div>

      <div className={styles.quotaLegend}>
        {MOCK_QUOTA_BY_USER.map((u) => (
          <div key={u.userId} className={styles.quotaLegendItem}>
            <span className={styles.quotaLegendDot} style={{ background: u.color }} />
            <span className={styles.quotaLegendName}>{u.name}</span>
            <span className={styles.quotaLegendCalls}>{u.calls}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
