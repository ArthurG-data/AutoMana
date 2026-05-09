import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ImagePicker } from '../ImagePicker'

vi.mock('../../api', () => ({
  uploadListingPicture: vi.fn(),
}))

import { uploadListingPicture } from '../../api'
const mockUpload = vi.mocked(uploadListingPicture)

describe('ImagePicker', () => {
  beforeEach(() => {
    mockUpload.mockReset()
  })

  it('renders existing image thumbnails', () => {
    render(
      <ImagePicker
        images={['https://example.com/img1.jpg', 'https://example.com/img2.jpg']}
        onChange={vi.fn()}
        appCode="automana_au"
      />
    )
    const imgs = screen.getAllByRole('img')
    expect(imgs).toHaveLength(2)
    expect(imgs[0]).toHaveAttribute('src', 'https://example.com/img1.jpg')
  })

  it('calls onChange with image removed on × click', async () => {
    const onChange = vi.fn()
    render(
      <ImagePicker
        images={['https://example.com/img1.jpg', 'https://example.com/img2.jpg']}
        onChange={onChange}
        appCode="automana_au"
      />
    )
    const removeBtns = screen.getAllByRole('button', { name: /remove/i })
    await userEvent.click(removeBtns[0])
    expect(onChange).toHaveBeenCalledWith(['https://example.com/img2.jpg'])
  })

  it('rejects invalid URL with inline error and does not call onChange', async () => {
    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)
    await userEvent.click(screen.getByRole('button', { name: /add url/i }))
    const input = screen.getByPlaceholderText(/https:\/\//i)
    await userEvent.type(input, 'not-a-url')
    await userEvent.click(screen.getByRole('button', { name: /^add$/i }))
    expect(screen.getByText(/must start with http/i)).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('appends valid URL to list via onChange', async () => {
    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)
    await userEvent.click(screen.getByRole('button', { name: /add url/i }))
    const input = screen.getByPlaceholderText(/https:\/\//i)
    await userEvent.type(input, 'https://example.com/card.jpg')
    await userEvent.click(screen.getByRole('button', { name: /^add$/i }))
    expect(onChange).toHaveBeenCalledWith(['https://example.com/card.jpg'])
  })

  it('shows spinner while uploading then calls onChange on success', async () => {
    let resolveUpload!: (v: { url: string }) => void
    mockUpload.mockReturnValue(new Promise<{ url: string }>((res) => { resolveUpload = res }))

    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([1])], 'photo.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(screen.getByTestId('upload-spinner')).toBeInTheDocument()

    resolveUpload({ url: 'https://i.ebayimg.com/photo.jpg' })
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(['https://i.ebayimg.com/photo.jpg'])
      expect(screen.queryByTestId('upload-spinner')).not.toBeInTheDocument()
    })
  })

  it('shows error slot with retry button on failed upload', async () => {
    mockUpload.mockRejectedValue(new Error('Network error'))

    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([1])], 'photo.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText(/upload failed/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('hides drop zone and add-url button when at maxImages limit', () => {
    const images = Array.from({ length: 3 }, (_, i) => `https://example.com/${i}.jpg`)
    render(
      <ImagePicker images={images} onChange={vi.fn()} appCode="automana_au" maxImages={3} />
    )
    expect(screen.queryByRole('button', { name: /add url/i })).not.toBeInTheDocument()
    expect(document.querySelector('input[type="file"]')).not.toBeInTheDocument()
  })

  it('accumulates multiple sequentially-uploaded images without losing earlier URLs', async () => {
    let resolve1!: (v: { url: string }) => void
    let resolve2!: (v: { url: string }) => void
    mockUpload
      .mockReturnValueOnce(new Promise<{ url: string }>((res) => { resolve1 = res }))
      .mockReturnValueOnce(new Promise<{ url: string }>((res) => { resolve2 = res }))

    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file1 = new File([new Uint8Array([1])], 'a.jpg', { type: 'image/jpeg' })
    const file2 = new File([new Uint8Array([2])], 'b.jpg', { type: 'image/jpeg' })

    // Fire both files at once (FileList with 2 files)
    fireEvent.change(fileInput, { target: { files: [file1, file2] } })

    resolve1({ url: 'https://i.ebayimg.com/a.jpg' })
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(['https://i.ebayimg.com/a.jpg'])
    })

    resolve2({ url: 'https://i.ebayimg.com/b.jpg' })
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith([
        'https://i.ebayimg.com/a.jpg',
        'https://i.ebayimg.com/b.jpg',
      ])
    })
  })

  it('retrying a failed upload re-attempts upload', async () => {
    mockUpload
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce({ url: 'https://i.ebayimg.com/ok.jpg' })

    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([1])], 'p.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => screen.getByRole('button', { name: /retry/i }))
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(['https://i.ebayimg.com/ok.jpg'])
    })
  })
})
