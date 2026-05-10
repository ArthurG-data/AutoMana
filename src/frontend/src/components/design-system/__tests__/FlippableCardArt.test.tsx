import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { FlippableCardArt } from '../FlippableCardArt'

vi.mock('../CardArt', () => ({
  CardArt: ({ name, imageUrl }: { name: string; imageUrl?: string | null }) => (
    <div data-testid="card-art" data-name={name} data-image={imageUrl ?? ''} />
  ),
}))

describe('FlippableCardArt', () => {
  it('renders the front image in the front face', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    const arts = screen.getAllByTestId('card-art')
    expect(arts[0].dataset.image).toBe('https://example.com/front.jpg')
  })

  it('renders the back image in the back face', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    const arts = screen.getAllByTestId('card-art')
    expect(arts[1].dataset.image).toBe('https://example.com/back.jpg')
  })

  it('renders a flip button when backUrl is provided', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    expect(screen.getByRole('button', { name: /flip/i })).toBeTruthy()
  })

  it('does not render a flip button when backUrl is null', () => {
    render(
      <FlippableCardArt
        name="Jace, the Mind Sculptor"
        frontUrl="https://example.com/front.jpg"
        backUrl={null}
      />
    )
    expect(screen.queryByRole('button', { name: /flip/i })).toBeNull()
  })

  it('does not render a back face when backUrl is null', () => {
    render(
      <FlippableCardArt
        name="Jace, the Mind Sculptor"
        frontUrl="https://example.com/front.jpg"
        backUrl={null}
      />
    )
    const arts = screen.getAllByTestId('card-art')
    expect(arts).toHaveLength(1)
  })

  it('adds the flipped data attribute after clicking the flip button', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    const card = screen.getByTestId('flip-card')
    expect(card.dataset.flipped).toBe('false')
    fireEvent.click(screen.getByRole('button', { name: /flip/i }))
    expect(card.dataset.flipped).toBe('true')
  })

  it('toggles flipped state back after clicking flip twice', () => {
    render(
      <FlippableCardArt
        name="Huntmaster of the Fells"
        frontUrl="https://example.com/front.jpg"
        backUrl="https://example.com/back.jpg"
      />
    )
    const card = screen.getByTestId('flip-card')
    const btn = screen.getByRole('button', { name: /flip/i })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(card.dataset.flipped).toBe('false')
  })
})
