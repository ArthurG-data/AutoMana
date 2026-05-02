import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Icon, type IconKind } from '../Icon'

const ALL_KINDS: IconKind[] = [
  'arrowUp','arrowDown','arrowRight','plus','search','chart','bell',
  'wallet','cards','eye','bag','moon','sun','flame','grid','list',
  'triangle','diamond','star','settings','more','sparkle','bot','flag','tag',
]

describe('Icon', () => {
  it.each(ALL_KINDS)('renders %s without crashing', (kind) => {
    const { container } = render(<Icon kind={kind} />)
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('applies custom size', () => {
    const { container } = render(<Icon kind="search" size={24} />)
    const svg = container.querySelector('svg')!
    expect(svg.getAttribute('width')).toBe('24')
    expect(svg.getAttribute('height')).toBe('24')
  })

  it('applies custom color', () => {
    const { container } = render(<Icon kind="search" color="#ff0000" />)
    const svg = container.querySelector('svg')!
    expect(svg.innerHTML).toContain('#ff0000')
  })
})
