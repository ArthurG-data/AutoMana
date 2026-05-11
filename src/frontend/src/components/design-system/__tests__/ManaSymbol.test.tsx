// src/frontend/src/components/design-system/__tests__/ManaSymbol.test.tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ManaSymbol, renderSymbolsInText } from '../ManaSymbol'

describe('ManaSymbol', () => {
  it('renders the basic ms class plus a lowercase symbol class', () => {
    const { container } = render(<ManaSymbol symbol="W" />)
    const i = container.querySelector('i')
    expect(i?.className).toContain('ms ')
    expect(i?.className).toContain('ms-w')
  })

  it('renders generic numbers as ms-N', () => {
    const { container } = render(<ManaSymbol symbol="3" />)
    expect(container.querySelector('i')?.className).toContain('ms-3')
  })

  it('renders X cost as ms-x', () => {
    const { container } = render(<ManaSymbol symbol="X" />)
    expect(container.querySelector('i')?.className).toContain('ms-x')
  })

  it('renders tap as ms-tap', () => {
    const { container } = render(<ManaSymbol symbol="T" />)
    expect(container.querySelector('i')?.className).toContain('ms-tap')
  })

  it('renders untap as ms-untap', () => {
    const { container } = render(<ManaSymbol symbol="Q" />)
    expect(container.querySelector('i')?.className).toContain('ms-untap')
  })

  it('strips the slash from hybrid symbols (W/U -> ms-wu)', () => {
    const { container } = render(<ManaSymbol symbol="W/U" />)
    expect(container.querySelector('i')?.className).toContain('ms-wu')
  })

  it('handles phyrexian (W/P -> ms-wp)', () => {
    const { container } = render(<ManaSymbol symbol="B/P" />)
    expect(container.querySelector('i')?.className).toContain('ms-bp')
  })

  it('handles 2-color hybrid (2/W -> ms-2w)', () => {
    const { container } = render(<ManaSymbol symbol="2/W" />)
    expect(container.querySelector('i')?.className).toContain('ms-2w')
  })

  it('adds ms-cost when cost prop is true (default)', () => {
    const { container } = render(<ManaSymbol symbol="R" />)
    expect(container.querySelector('i')?.className).toContain('ms-cost')
  })

  it('omits ms-cost when cost prop is false', () => {
    const { container } = render(<ManaSymbol symbol="R" cost={false} />)
    expect(container.querySelector('i')?.className).not.toContain('ms-cost')
  })

  it('sets fontSize to the size prop', () => {
    const { container } = render(<ManaSymbol symbol="R" size={20} />)
    expect((container.querySelector('i') as HTMLElement).style.fontSize).toBe('20px')
  })

  it('has an accessible label matching {symbol}', () => {
    const { container } = render(<ManaSymbol symbol="W/U" />)
    expect(container.querySelector('i')?.getAttribute('aria-label')).toBe('{W/U}')
  })
})

describe('renderSymbolsInText', () => {
  it('returns plain text as a single fragment when there are no symbols', () => {
    const out = renderSymbolsInText('Hello world')
    expect(out.length).toBe(1)
  })

  it('splits text and inserts ManaSymbol for each {token}', () => {
    const out = renderSymbolsInText('Add {R} or {G}.')
    const { container } = render(<div>{out}</div>)
    const symbols = container.querySelectorAll('i.ms')
    expect(symbols.length).toBe(2)
  })

  it('renders tap symbol from {T} inside text', () => {
    const { container } = render(
      <div>{renderSymbolsInText('{T}: Add {R}.')}</div>
    )
    expect(container.querySelector('i.ms-tap')).toBeTruthy()
    expect(container.querySelector('i.ms-r')).toBeTruthy()
  })

  it('preserves the text between symbols verbatim', () => {
    const { container } = render(
      <div>{renderSymbolsInText('Pay {2}{W}{W}: Do something.')}</div>
    )
    expect(container.textContent).toContain('Pay ')
    expect(container.textContent).toContain(': Do something.')
  })

  it('uses the inline (non-cost) variant by default', () => {
    const { container } = render(<div>{renderSymbolsInText('Add {R}.')}</div>)
    expect(container.querySelector('i.ms-r')?.className).not.toContain('ms-cost')
  })
})
