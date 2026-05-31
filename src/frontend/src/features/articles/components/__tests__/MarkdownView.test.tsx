import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MarkdownView } from '../MarkdownView'

describe('MarkdownView', () => {
  it('renders headings and paragraphs from markdown', () => {
    render(<MarkdownView markdown={'# Title\n\nSome **bold** text.'} />)
    expect(screen.getByRole('heading', { name: 'Title' })).toBeInTheDocument()
    expect(screen.getByText(/bold/)).toBeInTheDocument()
  })

  it('does not render raw HTML script tags', () => {
    const { container } = render(<MarkdownView markdown={'<script>alert(1)</script>hello'} />)
    expect(container.querySelector('script')).toBeNull()
  })
})
