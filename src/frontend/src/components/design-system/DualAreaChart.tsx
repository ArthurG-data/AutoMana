import { useState, useRef } from 'react'

interface DualAreaChartProps {
  listAvg: (number | null)[]
  soldAvg: (number | null)[]
  dates: Date[]
  width?: number
  height?: number
  listAvgColor?: string
  soldAvgColor?: string
}

const PAD = { top: 8, right: 8, bottom: 52, left: 52 }

function formatPrice(v: number): string {
  return v >= 10 ? `$${v.toFixed(0)}` : `$${v.toFixed(2)}`
}

function formatDate(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
}

function formatFullDate(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function DualAreaChart({
  listAvg,
  soldAvg,
  dates,
  width = 700,
  height = 200,
  listAvgColor = 'var(--hd-accent)',
  soldAvgColor = '#3b82f6',
}: DualAreaChartProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  const allValues = [...listAvg, ...soldAvg].filter((v) => v !== null) as number[]
  if (allValues.length < 2 || dates.length < 2) return null

  const cw = width - PAD.left - PAD.right
  const ch = height - PAD.top - PAD.bottom
  const n = dates.length

  const maxVal = Math.max(...allValues)
  const minY = 0
  const maxY = maxVal * 1.08
  const yRange = maxY - minY || 1

  const toX = (i: number) => PAD.left + (i / (n - 1)) * cw
  const toY = (v: number) => PAD.top + ch - ((v - minY) / yRange) * ch

  const Y_COUNT = 4
  const yTicks = Array.from({ length: Y_COUNT }, (_, i) => minY + (i / (Y_COUNT - 1)) * yRange)

  const xStep = n > 365 ? 365 : n > 90 ? 30 : n > 30 ? 7 : 1
  const xTicks: number[] = []
  for (let i = 0; i < n; i += xStep) xTicks.push(i)
  if (xTicks[xTicks.length - 1] !== n - 1) xTicks.push(n - 1)

  const linePath = (data: (number | null)[]): string => {
    const parts: string[] = []
    let open = false
    data.forEach((v, i) => {
      if (v === null) { open = false; return }
      parts.push(`${open ? 'L' : 'M'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
      open = true
    })
    return parts.join(' ')
  }

  const areaPath = (data: (number | null)[]): string => {
    const parts: string[] = []
    let segStart = -1
    const flush = (end: number) => {
      if (segStart === -1) return
      const seg = data.slice(segStart, end) as number[]
      const pts = seg.map((v, j) => `L${toX(segStart + j).toFixed(1)},${toY(v).toFixed(1)}`).join(' ')
      const x0 = toX(segStart).toFixed(1)
      const x1 = toX(end - 1).toFixed(1)
      const base = (PAD.top + ch).toFixed(1)
      parts.push(`M${x0},${base} ${pts} L${x1},${base} Z`)
      segStart = -1
    }
    data.forEach((v, i) => {
      if (v !== null && segStart === -1) segStart = i
      if (v === null && segStart !== -1) flush(i)
    })
    flush(data.length)
    return parts.join(' ')
  }

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const svgX = ((e.clientX - rect.left) / rect.width) * width
    const rawIdx = ((svgX - PAD.left) / cw) * (n - 1)
    setHoverIdx(Math.max(0, Math.min(n - 1, Math.round(rawIdx))))
  }

  const hoverListVal = hoverIdx !== null ? listAvg[hoverIdx] : null
  const hoverSoldVal = hoverIdx !== null ? soldAvg[hoverIdx] : null
  const hoverDate = hoverIdx !== null ? dates[hoverIdx] : null
  const crossX = hoverIdx !== null ? toX(hoverIdx) : null

  const labelStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 300,
    lineHeight: '1.7',
  }

  return (
    <div style={{ position: 'relative' }}>
      <svg
        ref={svgRef}
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        style={{ display: 'block', overflow: 'visible', cursor: 'crosshair' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverIdx(null)}
      >
        <defs>
          <linearGradient id="grad-list-avg" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={listAvgColor} stopOpacity="0.25" />
            <stop offset="100%" stopColor={listAvgColor} stopOpacity="0" />
          </linearGradient>
          <linearGradient id="grad-sold-avg" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={soldAvgColor} stopOpacity="0.25" />
            <stop offset="100%" stopColor={soldAvgColor} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Y grid lines + labels */}
        {yTicks.map((tick, i) => {
          const y = toY(tick)
          return (
            <g key={i}>
              <line x1={PAD.left} x2={PAD.left + cw} y1={y} y2={y} stroke="rgba(0,0,0,0.06)" strokeWidth="1" />
              <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize="8" fill="var(--hd-accent)" fontFamily="inherit" fontWeight="300" opacity="0.5">
                {formatPrice(tick)}
              </text>
            </g>
          )
        })}

        {/* X axis labels — rotated 90° */}
        {xTicks.map((idx, i) => {
          const x = toX(idx)
          const y = PAD.top + ch + 8
          return (
            <text key={i} x={x} y={y} textAnchor="end" fontSize="8" fill="var(--hd-accent)" fontFamily="inherit" fontWeight="300" opacity="0.5" transform={`rotate(-90, ${x}, ${y})`}>
              {formatDate(dates[idx])}
            </text>
          )
        })}

        {/* List Avg */}
        {areaPath(listAvg) && <path d={areaPath(listAvg)} fill="url(#grad-list-avg)" />}
        {linePath(listAvg) && <path d={linePath(listAvg)} fill="none" stroke={listAvgColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />}

        {/* Sold Avg */}
        {areaPath(soldAvg) && <path d={areaPath(soldAvg)} fill="url(#grad-sold-avg)" />}
        {linePath(soldAvg) && <path d={linePath(soldAvg)} fill="none" stroke={soldAvgColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />}

        {/* Crosshair */}
        {crossX !== null && hoverIdx !== null && (
          <g>
            <line x1={crossX} x2={crossX} y1={PAD.top} y2={PAD.top + ch} stroke="rgba(0,0,0,0.2)" strokeWidth="0.5" strokeDasharray="3,2" />
            {hoverListVal !== null && (
              <circle cx={crossX} cy={toY(hoverListVal)} r="3" fill={listAvgColor} />
            )}
            {hoverSoldVal !== null && (
              <circle cx={crossX} cy={toY(hoverSoldVal)} r="3" fill={soldAvgColor} />
            )}
          </g>
        )}
      </svg>

      {/* Hover info panel — top right */}
      {hoverDate !== null && (
        <div style={{
          position: 'absolute',
          top: 4,
          right: 4,
          background: 'var(--hd-card-bg, var(--hd-surface, #fff))',
          border: '1px solid var(--hd-border)',
          borderRadius: 6,
          padding: '6px 10px',
          pointerEvents: 'none',
          minWidth: 120,
        }}>
          <div style={{ ...labelStyle, color: 'var(--hd-accent)', opacity: 0.6, marginBottom: 2 }}>
            {formatFullDate(hoverDate)}
          </div>
          <div style={{ ...labelStyle, color: listAvgColor }}>
            List: {hoverListVal !== null ? formatPrice(hoverListVal) : '—'}
          </div>
          <div style={{ ...labelStyle, color: soldAvgColor }}>
            Sold: {hoverSoldVal !== null ? formatPrice(hoverSoldVal) : '—'}
          </div>
        </div>
      )}
    </div>
  )
}
