import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { DualAreaChart } from '../../../components/design-system/DualAreaChart'
import { cardPriceHistoryQueryOptions } from '../api'
import type { CardDetail } from '../types'
import styles from './PriceCharts.module.css'

interface PriceChartsProps {
  card: CardDetail
}

const TIME_RANGES = [
  { label: '1W', key: '1w' as const },
  { label: '1M', key: '1m' as const },
  { label: '3M', key: '3m' as const },
  { label: '1Y', key: '1y' as const },
  { label: 'ALL', key: 'all' as const },
]

export function PriceCharts({ card }: PriceChartsProps) {
  const [selectedRange, setSelectedRange] = useState<'1w' | '1m' | '3m' | '1y' | 'all'>('1m')

  const { data: priceData, isLoading } = useQuery(
    cardPriceHistoryQueryOptions(card.card_version_id, selectedRange)
  )

  // Data from API is already in dollars
  const listAvg = priceData?.price_history_list_avg ?? []
  const soldAvg = priceData?.price_history_sold_avg ?? []

  return (
    <div className={styles.chartSection}>
      <div className={styles.rangeSelector}>
        {TIME_RANGES.map((range) => (
          <button
            key={range.key}
            className={[
              styles.rangeBtn,
              selectedRange === range.key ? styles.rangeBtnActive : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => setSelectedRange(range.key)}
          >
            {range.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className={styles.loading}>Loading price data...</div>
      ) : listAvg.length > 0 && soldAvg.length > 0 ? (
        <>
          <DualAreaChart
            listAvg={listAvg}
            soldAvg={soldAvg}
            width={600}
            height={180}
          />
          <div className={styles.legend}>
            <span className={styles.legendItem}>
              <span style={{ color: 'var(--hd-accent)' }}>●</span> List Average
            </span>
            <span className={styles.legendItem}>
              <span style={{ color: '#3b82f6' }}>●</span> Sold Average
            </span>
          </div>
        </>
      ) : (
        <div className={styles.noData}>No price data available for this period</div>
      )}
    </div>
  )
}
