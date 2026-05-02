interface AreaChartProps {
  points: number[]
  color?: string
  width?: number
  height?: number
  gridColor?: string
}

export function AreaChart({
  points,
  color = '#10b981',
  width = 600,
  height = 180,
  gridColor = 'rgba(0,0,0,0.06)',
}: AreaChartProps) {
  if (!points || points.length < 2) return null

  const min = Math.min(...points) * 0.98
  const max = Math.max(...points) * 1.02
  const range = max - min || 1

  const coords = points.map((p, i) => [
    i * (width / (points.length - 1)),
    height - ((p - min) / range) * height,
  ])

  const linePath = coords
    .map((c, i) => `${i === 0 ? 'M' : 'L'}${c[0].toFixed(1)},${c[1].toFixed(1)}`)
    .join(' ')

  const areaPath = `${linePath} L${width},${height} L0,${height} Z`
  const gridRows = 4

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: 'block', overflow: 'visible' }}
    >
      <defs>
        <linearGradient id={`ac-grad-${color.replace('#', '')}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {Array.from({ length: gridRows + 1 }).map((_, i) => (
        <line
          key={i}
          x1="0"
          x2={width}
          y1={(i * height) / gridRows}
          y2={(i * height) / gridRows}
          stroke={gridColor}
          strokeWidth="1"
        />
      ))}
      <path d={areaPath} fill={`url(#ac-grad-${color.replace('#', '')})`} />
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
