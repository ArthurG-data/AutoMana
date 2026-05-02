import React from 'react'

export type IconKind =
  | 'arrowUp' | 'arrowDown' | 'arrowRight' | 'plus' | 'search'
  | 'chart' | 'bell' | 'wallet' | 'cards' | 'eye' | 'bag'
  | 'moon' | 'sun' | 'flame' | 'grid' | 'list' | 'triangle'
  | 'diamond' | 'star' | 'settings' | 'more' | 'sparkle'
  | 'bot' | 'flag' | 'tag'

interface IconProps {
  kind: IconKind
  size?: number
  color?: string
  strokeWidth?: number
}

export function Icon({
  kind,
  size = 16,
  color = 'currentColor',
  strokeWidth = 1.5,
}: IconProps) {
  const p = {
    stroke: color,
    strokeWidth,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    fill: 'none',
  }

  const paths: Record<IconKind, React.ReactNode> = {
    arrowUp:    <path d="M8 12 V4 M4 8 L8 4 L12 8" {...p} />,
    arrowDown:  <path d="M8 4 V12 M4 8 L8 12 L12 8" {...p} />,
    arrowRight: <path d="M3 8 H13 M9 4 L13 8 L9 12" {...p} />,
    plus:       <path d="M8 3 V13 M3 8 H13" {...p} />,
    search:     <g {...p}><circle cx="7" cy="7" r="4.2" /><path d="M10 10 L13 13" /></g>,
    chart:      <path d="M2 12 L6 8 L9 11 L14 4" {...p} />,
    bell:       <path d="M5 11 V7 a3 3 0 0 1 6 0 V11 H5 M7 13 a1 1 0 0 0 2 0" {...p} />,
    wallet:     <path d="M3 5 H12 a1 1 0 0 1 1 1 V11 a1 1 0 0 1 -1 1 H3 V5 Z M3 5 V12 M10 8.5 H12.5" {...p} />,
    cards:      <g {...p}><rect x="3" y="3" width="6" height="9" rx="1" /><rect x="7" y="4" width="6" height="9" rx="1" /></g>,
    eye:        <g {...p}><path d="M2 8 C 4 4 12 4 14 8 C 12 12 4 12 2 8 Z" /><circle cx="8" cy="8" r="2" /></g>,
    bag:        <path d="M4 6 H12 L11 13 H5 L4 6 Z M6 6 V4 a2 2 0 0 1 4 0 V6" {...p} />,
    moon:       <path d="M11.5 9.5 a4.5 4.5 0 1 1 -5 -7 a3.5 3.5 0 0 0 5 7 Z" {...p} />,
    sun:        <g {...p}><circle cx="8" cy="8" r="2.5" /><path d="M8 2 V3.5 M8 12.5 V14 M2 8 H3.5 M12.5 8 H14 M3.7 3.7 L4.8 4.8 M11.2 11.2 L12.3 12.3 M3.7 12.3 L4.8 11.2 M11.2 4.8 L12.3 3.7" /></g>,
    flame:      <path d="M8 14 c -3 0 -4.5 -2.2 -4.5 -4.5 c 0 -2 1.5 -3.5 2.5 -4.5 c 0 1.5 1 2 1.5 2 c 0 -2 1 -4 2.5 -5 c 0 2.5 3 4.5 3 7.5 c 0 2.3 -2 4.5 -5 4.5 Z" {...p} />,
    grid:       <g {...p}><rect x="3" y="3" width="4" height="4" /><rect x="9" y="3" width="4" height="4" /><rect x="3" y="9" width="4" height="4" /><rect x="9" y="9" width="4" height="4" /></g>,
    list:       <g {...p}><path d="M5 4 H13 M5 8 H13 M5 12 H13" /><circle cx="3" cy="4" r="0.6" fill={color} /><circle cx="3" cy="8" r="0.6" fill={color} /><circle cx="3" cy="12" r="0.6" fill={color} /></g>,
    triangle:   <path d="M8 4 L13 12 H3 Z" {...p} />,
    diamond:    <path d="M8 3 L13 8 L8 13 L3 8 Z" {...p} />,
    star:       <path d="M8 3 L9.5 6.8 L13.5 7 L10.3 9.5 L11.4 13.3 L8 11.1 L4.6 13.3 L5.7 9.5 L2.5 7 L6.5 6.8 Z" {...p} />,
    settings:   <g {...p}><circle cx="8" cy="8" r="2" /><path d="M8 2 V4 M8 12 V14 M14 8 H12 M4 8 H2 M12.2 3.8 L10.8 5.2 M5.2 10.8 L3.8 12.2 M3.8 3.8 L5.2 5.2 M10.8 10.8 L12.2 12.2" /></g>,
    more:       <g fill={color}><circle cx="4" cy="8" r="1.2" /><circle cx="8" cy="8" r="1.2" /><circle cx="12" cy="8" r="1.2" /></g>,
    sparkle:    <g {...p}><path d="M8 2 L9.4 6.6 L14 8 L9.4 9.4 L8 14 L6.6 9.4 L2 8 L6.6 6.6 Z" /><path d="M12.5 2.5 L13 4 L14.5 4.5 L13 5 L12.5 6.5 L12 5 L10.5 4.5 L12 4 Z" /></g>,
    bot:        <g {...p}><rect x="3" y="6" width="10" height="7" rx="1.5" /><path d="M8 3 V6 M5.5 3 H10.5" /><circle cx="6" cy="9.5" r="0.7" fill={color} /><circle cx="10" cy="9.5" r="0.7" fill={color} /></g>,
    flag:       <g {...p}><path d="M4 14 V3 M4 3 H12 L10 5.5 L12 8 H4" /></g>,
    tag:        <g {...p}><path d="M3 8 L8 3 H13 V8 L8 13 Z" /><circle cx="10" cy="6" r="0.7" fill={color} /></g>,
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      style={{ display: 'block', flex: '0 0 auto' }}
    >
      {paths[kind]}
    </svg>
  )
}
