// src/frontend/src/features/cards/components/__tests__/LegalityGrid.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LegalityGrid } from '../LegalityGrid'

const allLegal = {
  standard: 'legal',
  pioneer: 'legal',
  modern: 'legal',
  legacy: 'legal',
  vintage: 'legal',
  pauper: 'legal',
  commander: 'legal',
  oathbreaker: 'legal',
}

describe('LegalityGrid', () => {
  it('renders all 8 format labels', () => {
    render(<LegalityGrid legalities={allLegal} />)
    expect(screen.getByText('standard')).toBeTruthy()
    expect(screen.getByText('pioneer')).toBeTruthy()
    expect(screen.getByText('modern')).toBeTruthy()
    expect(screen.getByText('legacy')).toBeTruthy()
    expect(screen.getByText('vintage')).toBeTruthy()
    expect(screen.getByText('pauper')).toBeTruthy()
    expect(screen.getByText('commander')).toBeTruthy()
    expect(screen.getByText('oathbreaker')).toBeTruthy()
  })

  it('shows "legal" status text for legal formats', () => {
    render(<LegalityGrid legalities={allLegal} />)
    const cells = screen.getAllByText('legal')
    expect(cells.length).toBe(8)
  })

  it('shows "not legal" for not_legal formats (underscore replaced with space)', () => {
    render(<LegalityGrid legalities={{ ...allLegal, standard: 'not_legal', pauper: 'not_legal' }} />)
    const notLegalCells = screen.getAllByText('not legal')
    expect(notLegalCells.length).toBe(2)
  })

  it('shows "banned" status text for banned formats', () => {
    render(<LegalityGrid legalities={{ ...allLegal, modern: 'banned' }} />)
    expect(screen.getByText('banned')).toBeTruthy()
  })

  it('defaults missing formats to not_legal', () => {
    render(<LegalityGrid legalities={{}} />)
    const notLegalCells = screen.getAllByText('not legal')
    expect(notLegalCells.length).toBe(8)
  })

  it('shows "restricted" status text for restricted formats', () => {
    render(<LegalityGrid legalities={{ ...allLegal, vintage: 'restricted' }} />)
    expect(screen.getByText('restricted')).toBeTruthy()
  })
})
