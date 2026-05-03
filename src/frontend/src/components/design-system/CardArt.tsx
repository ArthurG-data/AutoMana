// src/frontend/src/components/design-system/CardArt.tsx
import React from 'react'

interface CardArtProps {
  name: string
  w?: number | string
  h?: number | string
  hue?: number
  label?: boolean
  imageUrl?: string | null
  style?: React.CSSProperties
}

export function CardArt({
  name,
  w = 200,
  h,
  hue = 30,
  label = true,
  imageUrl = null,
  style = {},
}: CardArtProps) {
  const seed = (name || 'card').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const stripeShift = (seed % 12) - 6
  const h2 = (hue + stripeShift + 360) % 360
  const sat = 8
  const lig = 18

  // When no explicit height is provided, use aspect-ratio so the container
  // scales correctly with responsive widths (MTG cards are 5:7).
  const heightStyle: React.CSSProperties = h !== undefined
    ? { height: h }
    : { aspectRatio: '5 / 7' }

  if (imageUrl) {
    return (
      <div
        style={{
          width: w,
          borderRadius: 6,
          position: 'relative',
          overflow: 'hidden',
          boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.06)',
          ...heightStyle,
          ...style,
        }}
      >
        <img
          src={imageUrl}
          alt={name}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
      </div>
    )
  }

  return (
    <div
      style={{
        width: w,
        borderRadius: 6,
        position: 'relative',
        background: `repeating-linear-gradient(
          135deg,
          hsl(${hue} ${sat}% ${lig}%) 0 8px,
          hsl(${h2} ${sat}% ${lig + 4}%) 8px 14px
        )`,
        overflow: 'hidden',
        boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.06)',
        fontFamily: 'var(--font-mono)',
        ...heightStyle,
        ...style,
      }}
    >
      {label && (
        <div
          style={{
            position: 'absolute',
            left: 8,
            right: 8,
            bottom: 8,
            fontSize: 9,
            color: 'rgba(255,255,255,0.55)',
            textTransform: 'uppercase',
            letterSpacing: 0.5,
          }}
        >
          {name}
        </div>
      )}
    </div>
  )
}
