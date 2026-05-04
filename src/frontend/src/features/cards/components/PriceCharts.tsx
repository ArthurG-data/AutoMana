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

function buildDates(startIso: string, count: number): Date[] {
  const start = new Date(startIso + 'T00:00:00')
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(start)
    d.setDate(d.getDate() + i)
    return d
  })
}

function trimNulls(
  list: (number | null)[],
  sold: (number | null)[],
  dates: Date[]
): { list: (number | null)[]; sold: (number | null)[]; dates: Date[] } {
  let first = 0
  let last = dates.length - 1
  while (first <= last && list[first] === null && sold[first] === null) first++
  while (last >= first && list[last] === null && sold[last] === null) last--
  return {
    list: list.slice(first, last + 1),
    sold: sold.slice(first, last + 1),
    dates: dates.slice(first, last + 1),
  }
}

export function PriceCharts({ card }: PriceChartsProps) {
  const [selectedRange, setSelectedRange] = useState<'1w' | '1m' | '3m' | '1y' | 'all'>('all')

  const { data: priceData, isLoading } = useQuery(
    cardPriceHistoryQueryOptions(card.card_version_id, selectedRange)
  )

  const rawList = priceData?.price_history_list_avg ?? []
  const rawSold = priceData?.price_history_sold_avg ?? []
  const rawDates = priceData?.date_range
    ? buildDates(priceData.date_range.start, rawList.length)
    : []

  const { list: listAvg, sold: soldAvg, dates } = trimNulls(rawList, rawSold, rawDates)
  const hasData = [...listAvg, ...soldAvg].filter((v) => v !== null).length >= 2

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
      ) : hasData ? (
        <>
          <DualAreaChart
            listAvg={listAvg}
            soldAvg={soldAvg}
            dates={dates}
            height={200}
          />
          <div className={styles.legend}>
            <span className={styles.legendItem}>
              <span style={{ color: 'var(--hd-accent)' }}>●</span> List Avg
            </span>
            <span className={styles.legendItem}>
              <span style={{ color: '#3b82f6' }}>●</span> Sold Avg
            </span>
          </div>
        </>
      ) : (
        <div className={styles.noData}>
          No price data for this period
          {selectedRange !== 'all' && (
            <button className={styles.fallbackBtn} onClick={() => setSelectedRange('all')}>
              View full history
            </button>
          )}
        </div>
      )}
    </div>
  )
}
