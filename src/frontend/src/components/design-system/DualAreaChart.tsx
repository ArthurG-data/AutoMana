interface DualAreaChartProps {
  listAvg: (number | null)[]
  soldAvg: (number | null)[]
  width?: number
  height?: number
  listAvgColor?: string
  soldAvgColor?: string
  gridColor?: string
}

export function DualAreaChart({
  listAvg,
  soldAvg,
  width = 600,
  height = 180,
  listAvgColor = 'var(--hd-accent)',
  soldAvgColor = '#3b82f6',
  gridColor = 'rgba(0,0,0,0.06)',
}: DualAreaChartProps) {
  // Filter null values for scaling
  const allValues = [...listAvg, ...soldAvg].filter((v) => v !== null) as number[]
  if (allValues.length < 2) return null

  const min = Math.min(...allValues) * 0.98
  const max = Math.max(...allValues) * 1.02
  const range = max - min || 1

  const generatePath = (data: (number | null)[]): string => {
    const coords = data
      .map((value, i) => {
        if (value === null) return null
        return [
          i * (width / (data.length - 1)),
          height - ((value - min) / range) * height,
        ]
      })
      .filter((c) => c !== null) as [number, number][]

    if (coords.length === 0) return ''

    return coords
      .map((c, i) => `${i === 0 ? 'M' : 'L'}${c[0].toFixed(1)},${c[1].toFixed(1)}`)
      .join(' ')
  }

  const listAvgPath = generatePath(listAvg)
  const soldAvgPath = generatePath(soldAvg)

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: 'block', overflow: 'visible' }}
    >
      <defs>
        <linearGradient id="grad-list-avg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={listAvgColor} stopOpacity="0.28" />
          <stop offset="100%" stopColor={listAvgColor} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="grad-sold-avg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={soldAvgColor} stopOpacity="0.28" />
          <stop offset="100%" stopColor={soldAvgColor} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {Array.from({ length: 5 }).map((_, i) => (
        <line
          key={i}
          x1="0"
          x2={width}
          y1={(i * height) / 4}
          y2={(i * height) / 4}
          stroke={gridColor}
          strokeWidth="1"
        />
      ))}

      {/* List Avg area */}
      {listAvgPath && (
        <>
          <path
            d={listAvgPath + ` L${width},${height} L0,${height} Z`}
            fill="url(#grad-list-avg)"
          />
          <path
            d={listAvgPath}
            fill="none"
            stroke={listAvgColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}

      {/* Sold Avg area */}
      {soldAvgPath && (
        <>
          <path
            d={soldAvgPath + ` L${width},${height} L0,${height} Z`}
            fill="url(#grad-sold-avg)"
          />
          <path
            d={soldAvgPath}
            fill="none"
            stroke={soldAvgColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}
    </svg>
  )
}
