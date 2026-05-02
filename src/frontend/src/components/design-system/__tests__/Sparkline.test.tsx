import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Sparkline } from '../Sparkline'

describe('Sparkline', () => {
  it('returns null for fewer than 2 points', () => {
    const { container } = render(<Sparkline points={[42]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders an SVG for valid points', () => {
    const pts = [10, 20, 15, 25, 18]
    const { container } = render(<Sparkline points={pts} />)
    expect(container.querySelector('svg')).toBeTruthy()
    expect(container.querySelector('path')).toBeTruthy()
  })

  it('renders area path when fill=true', () => {
    const pts = [10, 20, 15, 25]
    const { container } = render(<Sparkline points={pts} fill />)
    const paths = container.querySelectorAll('path')
    expect(paths.length).toBe(2) // line + area
  })

  it('does not render area path when fill=false', () => {
    const pts = [10, 20, 15, 25]
    const { container } = render(<Sparkline points={pts} fill={false} />)
    const paths = container.querySelectorAll('path')
    expect(paths.length).toBe(1)
  })
})
