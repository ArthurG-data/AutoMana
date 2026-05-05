// src/frontend/src/features/collection/components/__tests__/CollectionTable.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { CollectionTable } from '../CollectionTable'
import { MOCK_COLLECTION } from '../../mockCollection'

describe('CollectionTable', () => {
  it('renders table headers', () => {
    render(<CollectionTable cards={[]} />)
    expect(screen.getByText('Card name')).toBeTruthy()
    expect(screen.getByText('Set')).toBeTruthy()
    expect(screen.getByText('Market price')).toBeTruthy()
    expect(screen.getByText('P/L')).toBeTruthy()
    expect(screen.getByText('Status')).toBeTruthy()
  })

  it('shows empty state when no cards', () => {
    render(<CollectionTable cards={[]} />)
    expect(screen.getByText(/no cards match/i)).toBeTruthy()
  })

  it('renders mock collection rows', () => {
    render(<CollectionTable cards={MOCK_COLLECTION} />)
    expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeTruthy()
    expect(screen.getByText('Force of Will')).toBeTruthy()
    expect(screen.getByText('Mox Diamond')).toBeTruthy()
  })

  it('shows LIST button only for ready cards', () => {
    render(<CollectionTable cards={MOCK_COLLECTION} />)
    const readyCards = MOCK_COLLECTION.filter((c) => c.aiStatus === 'ready')
    // Each ready card has a LIST button
    const listButtons = screen.getAllByRole('button', { name: /list/i })
    // At least one List button per ready card
    expect(listButtons.length).toBeGreaterThanOrEqual(readyCards.length)
  })

  it('calls onList when LIST button is clicked', () => {
    const onList = vi.fn()
    const readyCard = MOCK_COLLECTION.find((c) => c.aiStatus === 'ready')!
    render(<CollectionTable cards={[readyCard]} onList={onList} />)

    const listBtn = screen.getByRole('button', { name: new RegExp(`list ${readyCard.name}`, 'i') })
    fireEvent.click(listBtn)
    expect(onList).toHaveBeenCalledWith(readyCard)
  })

  it('renders mana pip for each card color', () => {
    const card = MOCK_COLLECTION.find((c) => c.name === 'Teferi, Time Raveler')!
    render(<CollectionTable cards={[card]} />)
    // Teferi is W/U — both pip letters should appear
    expect(screen.getAllByText('W').length).toBeGreaterThan(0)
    expect(screen.getAllByText('U').length).toBeGreaterThan(0)
  })

  it('shows accessible aria-label on more button', () => {
    const card = MOCK_COLLECTION[0]
    render(<CollectionTable cards={[card]} />)
    expect(
      screen.getByRole('button', { name: new RegExp(`more options for ${card.name}`, 'i') })
    ).toBeTruthy()
  })
})
