import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SetCard } from '../SetCard'
import type { SetBrowseItem } from '../../types'

const mockSet: SetBrowseItem = {
  set_id: '11111111-1111-1111-1111-111111111111',
  set_name: 'Murders at Karlov Manor',
  set_code: 'mkm',
  set_type: 'expansion',
  card_count: 286,
  released_at: '2024-02-09',
  icon_svg_uri: 'http://example.com/mkm.svg',
  parent_set_code: null,
  key_art_uri: null,
}

describe('SetCard', () => {
  it('renders set code uppercased', () => {
    render(<SetCard set={mockSet} onSelect={vi.fn()} />)
    expect(screen.getByText('MKM')).toBeTruthy()
  })

  it('renders prettified set type', () => {
    render(<SetCard set={mockSet} onSelect={vi.fn()} />)
    expect(screen.getByText('Expansion')).toBeTruthy()
  })

  it('renders card count', () => {
    render(<SetCard set={mockSet} onSelect={vi.fn()} />)
    expect(screen.getByText('286')).toBeTruthy()
  })

  it('renders set name in the art area', () => {
    render(<SetCard set={mockSet} onSelect={vi.fn()} />)
    expect(screen.getByText('Murders at Karlov Manor')).toBeTruthy()
  })

  it('calls onSelect with set_code when clicked', () => {
    const onSelect = vi.fn()
    const { container } = render(<SetCard set={mockSet} onSelect={onSelect} />)
    fireEvent.click(container.querySelector('button')!)
    expect(onSelect).toHaveBeenCalledWith('mkm')
  })

  it('shows fallback svg when image errors', () => {
    const { container } = render(<SetCard set={mockSet} onSelect={vi.fn()} />)
    const img = container.querySelector('img')!
    fireEvent.error(img)
    expect(container.querySelector('svg')).toBeTruthy()
    expect(container.querySelector('img')).toBeNull()
  })

  it('applies childCard class when isChild is true', () => {
    const { container } = render(<SetCard set={mockSet} isChild onSelect={vi.fn()} />)
    const btn = container.querySelector('button')!
    expect(btn.className).toMatch(/childCard/)
  })

  it('does not render bgArt div when key_art_uri is null', () => {
    const { container } = render(<SetCard set={mockSet} onSelect={vi.fn()} />)
    expect(container.querySelector('[class*="bgArt"]')).toBeNull()
  })

  it('renders bgArt div with backgroundImage when key_art_uri is provided', () => {
    const setWithArt: SetBrowseItem = {
      ...mockSet,
      key_art_uri: 'https://cards.scryfall.io/art_crop/front/a/b/ab12.jpg',
    }
    const { container } = render(<SetCard set={setWithArt} onSelect={vi.fn()} />)
    const bgArt = container.querySelector('[class*="bgArt"]') as HTMLElement
    expect(bgArt).not.toBeNull()
    expect(bgArt.style.backgroundImage).toMatch(
      /url\(["']?https:\/\/cards\.scryfall\.io\/art_crop\/front\/a\/b\/ab12\.jpg["']?\)/
    )
  })

  it('shows UPCOMING badge when released_at is in the future', () => {
    const futureSet: SetBrowseItem = {
      ...mockSet,
      released_at: '2099-01-01',
    }
    render(<SetCard set={futureSet} onSelect={vi.fn()} />)
    expect(screen.getByText('UPCOMING')).toBeTruthy()
  })

  it('does not show UPCOMING badge for past sets', () => {
    render(<SetCard set={mockSet} onSelect={vi.fn()} />)
    expect(screen.queryByText('UPCOMING')).toBeNull()
  })

  it('applies upcoming class when released_at is in the future', () => {
    const futureSet: SetBrowseItem = { ...mockSet, released_at: '2099-01-01' }
    const { container } = render(<SetCard set={futureSet} onSelect={vi.fn()} />)
    expect(container.querySelector('button')!.className).toMatch(/upcoming/)
  })
})
