import { useState, useRef } from 'react'
import { uploadListingPicture } from '../api'
import styles from './ImagePicker.module.css'

interface ImagePickerProps {
  images: string[]
  onChange: (images: string[]) => void
  appCode: string
  maxImages?: number
}

interface UploadSlot {
  id: string
  status: 'uploading' | 'error'
  file: File
  error?: string
}

export function ImagePicker({ images, onChange, appCode, maxImages = 12 }: ImagePickerProps) {
  const [slots, setSlots] = useState<UploadSlot[]>([])
  const [urlInputVisible, setUrlInputVisible] = useState(false)
  const [urlInput, setUrlInput] = useState('')
  const [urlError, setUrlError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const uploadingCount = slots.filter((s) => s.status === 'uploading').length
  const atLimit = images.length + uploadingCount >= maxImages

  async function uploadFile(file: File) {
    const id = crypto.randomUUID()
    setSlots((prev) => [...prev, { id, status: 'uploading', file }])
    try {
      const { url } = await uploadListingPicture(appCode, file)
      onChange([...images, url])
      setSlots((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      setSlots((prev) =>
        prev.map((s) =>
          s.id === id
            ? { ...s, status: 'error', error: err instanceof Error ? err.message : 'Upload failed' }
            : s
        )
      )
    }
  }

  async function handleFiles(files: FileList | null) {
    if (!files) return
    for (const file of Array.from(files)) {
      await uploadFile(file)
    }
  }

  function handleRetry(slot: UploadSlot) {
    setSlots((prev) => prev.filter((s) => s.id !== slot.id))
    uploadFile(slot.file)
  }

  function handleAddUrl() {
    const url = urlInput.trim()
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setUrlError('URL must start with http:// or https://')
      return
    }
    onChange([...images, url])
    setUrlInput('')
    setUrlInputVisible(false)
    setUrlError(null)
  }

  return (
    <div className={styles.picker}>
      <div className={styles.grid}>
        {images.map((url, i) => (
          <div key={url} className={styles.thumb}>
            <img src={url} alt={`Image ${i + 1}`} className={styles.thumbImg} />
            <button
              type="button"
              aria-label="Remove image"
              className={styles.removeBtn}
              onClick={() => onChange(images.filter((_, idx) => idx !== i))}
            >
              ×
            </button>
          </div>
        ))}

        {slots.map((slot) =>
          slot.status === 'uploading' ? (
            <div key={slot.id} className={styles.slotUploading}>
              <div className={styles.spinner} data-testid="upload-spinner" />
            </div>
          ) : (
            <div key={slot.id} className={styles.slotError}>
              <span>Upload failed</span>
              <button
                type="button"
                aria-label="Retry upload"
                className={styles.retryBtn}
                onClick={() => handleRetry(slot)}
              >
                Retry
              </button>
            </div>
          )
        )}

        {!atLimit && (
          <>
            <button
              type="button"
              aria-label="Add image"
              className={[styles.dropZone, dragging ? styles.dropZoneDragging : ''].filter(Boolean).join(' ')}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                handleFiles(e.dataTransfer.files)
              }}
            >
              <span className={styles.dropZoneIcon} aria-hidden>+</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className={styles.fileInput}
              onChange={(e) => handleFiles(e.target.files)}
            />
          </>
        )}
      </div>

      {!atLimit && (
        <div className={styles.controls}>
          {!urlInputVisible ? (
            <button
              type="button"
              className={styles.addUrlBtn}
              onClick={() => setUrlInputVisible(true)}
            >
              + Add URL
            </button>
          ) : (
            <div>
              <div className={styles.urlInputRow}>
                <input
                  type="text"
                  className={styles.urlInput}
                  value={urlInput}
                  onChange={(e) => { setUrlInput(e.target.value); setUrlError(null) }}
                  placeholder="https://..."
                  onKeyDown={(e) => e.key === 'Enter' && handleAddUrl()}
                  autoFocus
                />
                <button type="button" className={styles.addBtn} onClick={handleAddUrl}>
                  Add
                </button>
              </div>
              {urlError && <div className={styles.urlError}>{urlError}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
