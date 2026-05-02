import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { SuggestionsDropdown } from '../SuggestionsDropdown'
import type { CardSuggestion } from '../../../features/cards/types'

describe('SuggestionsDropdown', () => {
  const mockSuggestions: CardSuggestion[] = [
    { card_version_id: '1', card_name: 'Ragavan, Nimble Pilferer', set_code: 'MH2', collector_number: '1', rarity_name: 'mythic', score: 1.0 },
    { card_version_id: '2', card_name: 'Raggetha', set_code: 'ZEN', collector_number: '2', rarity_name: 'rare', score: 0.8 },
  ]

  it('does not render when isOpen is false', () => {
    render(
      <SuggestionsDropdown
        suggestions={mockSuggestions}
        selectedIndex={0}
        onSelect={vi.fn()}
        isOpen={false}
      />
    )

    expect(screen.queryByText('Ragavan, Nimble Pilferer')).not.toBeInTheDocument()
  })

  it('renders dropdown with suggestions when isOpen is true', () => {
    render(
      <SuggestionsDropdown
        suggestions={mockSuggestions}
        selectedIndex={0}
        onSelect={vi.fn()}
        isOpen={true}
      />
    )

    expect(screen.getByText('Ragavan, Nimble Pilferer')).toBeInTheDocument()
    expect(screen.getByText('Raggetha')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    render(
      <SuggestionsDropdown
        suggestions={[]}
        selectedIndex={0}
        onSelect={vi.fn()}
        isLoading={true}
        isOpen={true}
      />
    )

    expect(screen.getByText('Loading suggestions...')).toBeInTheDocument()
  })

  it('shows empty state when no suggestions', () => {
    render(
      <SuggestionsDropdown
        suggestions={[]}
        selectedIndex={0}
        onSelect={vi.fn()}
        isLoading={false}
        isOpen={true}
      />
    )

    expect(screen.getByText('No cards found')).toBeInTheDocument()
  })

  it('highlights selected suggestion', () => {
    const { container } = render(
      <SuggestionsDropdown
        suggestions={mockSuggestions}
        selectedIndex={0}
        onSelect={vi.fn()}
        isOpen={true}
      />
    )

    const buttons = container.querySelectorAll('button')
    expect(buttons[0].className).toContain('selected')
  })

  it('calls onSelect when suggestion is clicked', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()

    render(
      <SuggestionsDropdown
        suggestions={mockSuggestions}
        selectedIndex={0}
        onSelect={onSelect}
        isOpen={true}
      />
    )

    const button = screen.getByText('Ragavan, Nimble Pilferer')
    await user.click(button)

    expect(onSelect).toHaveBeenCalledWith(mockSuggestions[0])
  })
})
