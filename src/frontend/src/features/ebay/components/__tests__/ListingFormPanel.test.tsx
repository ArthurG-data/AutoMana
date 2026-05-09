import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ListingFormPanel } from '../ListingFormPanel'
import type { EbayAppSummary } from '../../api'

vi.mock('../ImagePicker', () => ({
  ImagePicker: ({
    images,
    onChange,
  }: {
    images: string[]
    onChange: (imgs: string[]) => void
  }) => (
    <div data-testid="image-picker" data-images={images.join(',')}>
      <button onClick={() => onChange([...images, 'https://new.jpg'])}>
        Add image
      </button>
    </div>
  ),
}))

function makeApp(overrides: Partial<EbayAppSummary> = {}): EbayAppSummary {
  return {
    app_id: 'a1',
    app_name: 'AutoMana AU',
    app_code: 'automana_au',
    environment: 'PRODUCTION',
    description: null,
    is_active: true,
    is_connected: true,
    token_expires_at: null,
    other_user_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('ListingFormPanel', () => {
  it('pre-fills fields from initialValues', () => {
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Sheoldred MOM NM', price: 55, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    expect(screen.getByDisplayValue('Sheoldred MOM NM')).toBeInTheDocument()
    expect(screen.getByDisplayValue('55')).toBeInTheDocument()
    expect(screen.getByDisplayValue('1')).toBeInTheDocument()
  })

  it('calls onCancel when Cancel is clicked', async () => {
    const onCancel = vi.fn()
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Test', price: 10, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={vi.fn()}
        onCancel={onCancel}
        isSaving={false}
        error={null}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onSave with current values when Save is clicked', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Ragavan MH2 NM', price: 62, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={onSave}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    expect(onSave).toHaveBeenCalledWith(
      { title: 'Ragavan MH2 NM', price: 62, quantity: 1, conditionId: 3000, description: '' },
      'automana_au',
    )
  })

  it('shows error message when error prop is set', () => {
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Test', price: 10, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={false}
        error="eBay API error: token expired"
      />
    )
    expect(screen.getByText('eBay API error: token expired')).toBeInTheDocument()
  })

  it('disables Save button while isSaving', () => {
    render(
      <ListingFormPanel
        mode="edit"
        initialValues={{ title: 'Test', price: 10, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        appCode="automana_au"
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={true}
        error={null}
      />
    )
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
  })

  it('shows app dropdown in create mode', () => {
    render(
      <ListingFormPanel
        mode="create"
        initialValues={{}}
        availableApps={[makeApp(), makeApp({ app_code: 'app2', app_name: 'App 2' })]}
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    expect(screen.getByRole('combobox', { name: /app/i })).toBeInTheDocument()
  })

  it('validates price must be > 0 before calling onSave', async () => {
    const onSave = vi.fn()
    render(
      <ListingFormPanel
        mode="create"
        initialValues={{ title: 'Test', price: 0, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        onSave={onSave}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByText(/price must be greater than 0/i)).toBeInTheDocument()
  })

  it('calls onSave with the selected app_code in create mode', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <ListingFormPanel
        mode="create"
        initialValues={{ title: 'Ragavan MH2 NM', price: 62, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp(), makeApp({ app_code: 'app2', app_name: 'App 2' })]}
        onSave={onSave}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
      />
    )
    await userEvent.selectOptions(screen.getByRole('combobox', { name: /app/i }), 'app2')
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Ragavan MH2 NM' }),
      'app2',
    )
  })

  it('renders ImagePicker with provided imageUrls', () => {
    render(
      <ListingFormPanel
        mode="create"
        initialValues={{ title: 'Card NM MTG', price: 10, quantity: 1, conditionId: 3000, description: '' }}
        availableApps={[makeApp()]}
        onSave={vi.fn()}
        onCancel={vi.fn()}
        isSaving={false}
        error={null}
        imageUrls={['https://example.com/img.jpg']}
        onImageChange={vi.fn()}
        appCode="automana_au"
      />
    )
    const picker = screen.getByTestId('image-picker')
    expect(picker).toBeInTheDocument()
    expect(picker.getAttribute('data-images')).toBe('https://example.com/img.jpg')
  })
})
