interface SparklineProps {
  points: number[]
  color?: string
  width?: number
  height?: number
  strokeWidth?: number
  fill?: boolean
}

export function Sparkline({
  points,
  color = 'currentColor',
  width = 120,
  height = 32,
  strokeWidth = 1.5,
  fill = false,
}: SparklineProps) {
  if (!points || points.length < 2) return null

  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = max - min || 1
  const stepX = width / (points.length - 1)

  const coords = points.map((p, i) => ({
    x: +(i * stepX).toFixed(2),
    y: +(height - ((p - min) / range) * height).toFixed(2),
  }))

  const linePath = coords
    .map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x},${c.y}`)
    .join(' ')

  const areaPath = linePath + ` L${width},${height} L0,${height} Z`

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: 'block', overflow: 'visible' }}
    >
      {fill && (
        <path d={areaPath} fill={color} opacity="0.12" />
      )}
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
