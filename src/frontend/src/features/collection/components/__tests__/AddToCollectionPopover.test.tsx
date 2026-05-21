import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AddToCollectionPopover } from '../AddToCollectionPopover'
import type { Collection } from '../../api'

const COLLECTIONS: Collection[] = [
  {
    collection_id: 'col1',
    collection_name: 'My Collection',
    description: '',
    is_active: true,
    created_at: '2024-01-01T00:00:00',
    username: 'testuser',
  },
  {
    collection_id: 'col2',
    collection_name: 'Trade Binder',
    description: '',
    is_active: true,
    created_at: '2024-01-01T00:00:00',
    username: 'testuser',
  },
]

describe('AddToCollectionPopover', () => {
  it('renders condition pills', () => {
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="non-foil"
        collections={COLLECTIONS}
        onAdd={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: 'NM' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'LP' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'MP' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'HP' })).toBeTruthy()
  })

  it('shows finish as read-only label', () => {
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="foil"
        collections={COLLECTIONS}
        onAdd={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByText('foil')).toBeTruthy()
  })

  it('shows collection options in select', () => {
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="non-foil"
        collections={COLLECTIONS}
        onAdd={vi.fn()}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByRole('option', { name: 'My Collection' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Trade Binder' })).toBeTruthy()
  })

  it('calls onAdd with selected values on submit', () => {
    const onAdd = vi.fn()
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="non-foil"
        collections={COLLECTIONS}
        onAdd={onAdd}
        onClose={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'LP' }))
    fireEvent.click(screen.getByRole('button', { name: /add to collection/i }))
    expect(onAdd).toHaveBeenCalledWith({
      collectionId: 'col1',
      condition: 'LP',
      finish: 'NONFOIL',
    })
  })

  it('calls onClose when cancel is clicked', () => {
    const onClose = vi.fn()
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="non-foil"
        collections={COLLECTIONS}
        onAdd={vi.fn()}
        onClose={onClose}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('hides dropdown with single collection and still submits correctly', () => {
    const onAdd = vi.fn()
    render(
      <AddToCollectionPopover
        cardVersionId="cv1"
        cardName="Ragavan"
        finish="foil"
        collections={[COLLECTIONS[0]]}
        onAdd={onAdd}
        onClose={vi.fn()}
      />
    )
    expect(screen.queryByRole('combobox')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /add to collection/i }))
    expect(onAdd).toHaveBeenCalledWith({
      collectionId: 'col1',
      condition: 'NM',
      finish: 'FOIL',
    })
  })
})
