import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Pip, type ManaColor } from '../Pip'

const COLORS: ManaColor[] = ['W', 'U', 'B', 'R', 'G', 'C']

describe('Pip', () => {
  it.each(COLORS)('renders %s pip without crashing', (color) => {
    const { container } = render(<Pip color={color} />)
    expect(container.firstChild).toBeTruthy()
  })

  it('shows color letter for W', () => {
    const { getByText } = render(<Pip color="W" />)
    expect(getByText('W')).toBeTruthy()
  })

  it('shows empty string for C (colorless)', () => {
    const { container } = render(<Pip color="C" />)
    expect(container.textContent).toBe('')
  })

  it('applies custom size', () => {
    const { container } = render(<Pip color="U" size={20} />)
    const span = container.firstChild as HTMLElement
    expect(span.style.width).toBe('20px')
    expect(span.style.height).toBe('20px')
  })
})
