// src/frontend/src/features/ebay/components/ListingFormPanel.tsx
import { useState } from 'react'
import type { EbayAppSummary } from '../api'
import styles from './ListingFormPanel.module.css'
import { ImagePicker } from './ImagePicker'

export interface ListingFormValues {
  title: string
  price: number
  quantity: number
  conditionId: number
  description: string
}

export const CONDITION_OPTIONS = [
  { label: 'Near Mint (NM)', value: 3000 },
  { label: 'Lightly Played (LP)', value: 4000 },
  { label: 'Moderately Played (MP)', value: 5000 },
  { label: 'Heavily Played (HP)', value: 6000 },
  { label: 'Damaged (DMG)', value: 7000 },
]

interface ListingFormPanelProps {
  mode: 'create' | 'edit'
  initialValues: Partial<ListingFormValues>
  availableApps: EbayAppSummary[]
  appCode?: string
  imageUrls?: string[]
  onImageChange?: (urls: string[]) => void
  onSave: (values: ListingFormValues, appCode: string) => Promise<void>
  onCancel: () => void
  isSaving: boolean
  error: string | null
}

export function ListingFormPanel({
  mode,
  initialValues,
  availableApps,
  appCode: fixedAppCode,
  imageUrls = [],
  onImageChange,
  onSave,
  onCancel,
  isSaving,
  error,
}: ListingFormPanelProps) {
  const [title, setTitle] = useState(initialValues.title ?? '')
  const [price, setPrice] = useState(initialValues.price ?? 0)
  const [quantity, setQuantity] = useState(initialValues.quantity ?? 1)
  const [conditionId, setConditionId] = useState(initialValues.conditionId ?? 3000)
  const [description, setDescription] = useState(initialValues.description ?? '')
  const [selectedAppCode, setSelectedAppCode] = useState(
    fixedAppCode ?? availableApps[0]?.app_code ?? '',
  )
  const [validationError, setValidationError] = useState<string | null>(null)

  function validate(): boolean {
    if (price <= 0) {
      setValidationError('Price must be greater than 0')
      return false
    }
    if (quantity < 1) {
      setValidationError('Quantity must be at least 1')
      return false
    }
    if (!title.trim()) {
      setValidationError('Title is required')
      return false
    }
    setValidationError(null)
    return true
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    await onSave(
      { title: title.trim(), price, quantity, conditionId, description },
      selectedAppCode,
    )
  }

  const saveLabel = mode === 'create' ? 'Create listing' : 'Save changes'
  const displayError = validationError ?? error

  return (
    <form onSubmit={handleSubmit} className={styles.form} noValidate>
      <div className={styles.header}>
        <span className={styles.title}>
          {mode === 'create' ? 'New listing' : 'Edit listing'}
        </span>
      </div>

      <div className={styles.fields}>
        <label className={styles.field}>
          <span className={styles.label}>Title</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={80}
            className={styles.input}
            placeholder="Card name + set + condition"
          />
        </label>

        <div className={styles.row}>
          <label className={styles.field}>
            <span className={styles.label}>Price (AUD)</span>
            <input
              type="number"
              value={price}
              onChange={(e) => setPrice(Number(e.target.value))}
              step="0.01"
              min="0.01"
              className={styles.input}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Qty</span>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              step="1"
              min="1"
              className={styles.inputSmall}
            />
          </label>
        </div>

        <label className={styles.field}>
          <span className={styles.label}>Condition</span>
          <select
            value={conditionId}
            onChange={(e) => setConditionId(Number(e.target.value))}
            className={styles.select}
          >
            {CONDITION_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Description (optional)</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={500}
            rows={3}
            className={styles.textarea}
            placeholder="Any extra notes for the buyer"
          />
        </label>

        {onImageChange && (
          <div className={styles.field}>
            <span className={styles.label}>Images (up to 12)</span>
            <ImagePicker
              images={imageUrls}
              onChange={onImageChange}
              appCode={fixedAppCode ?? selectedAppCode}
            />
          </div>
        )}

        {mode === 'create' && (
          <label className={styles.field} aria-label="App">
            <span className={styles.label}>App</span>
            <select
              value={selectedAppCode}
              onChange={(e) => setSelectedAppCode(e.target.value)}
              className={styles.select}
            >
              {availableApps.map((app) => (
                <option key={app.app_code} value={app.app_code}>
                  {app.app_name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {displayError && (
        <div className={styles.error} role="alert">
          {displayError}
        </div>
      )}

      <div className={styles.actions}>
        <button type="button" onClick={onCancel} className={styles.cancelBtn}>
          Cancel
        </button>
        <button type="submit" disabled={isSaving} className={styles.saveBtn}>
          {isSaving ? 'Saving…' : saveLabel}
        </button>
      </div>
    </form>
  )
}
