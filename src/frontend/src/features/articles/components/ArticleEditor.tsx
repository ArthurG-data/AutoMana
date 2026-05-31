import { useState } from 'react'
import { MarkdownView } from './MarkdownView'
import type { Article, ArticleCreate } from '../types'
import styles from './ArticleEditor.module.css'

interface ArticleEditorProps {
  initial?: Article
  onSave: (payload: ArticleCreate) => void
  saving?: boolean
}

// Editorial guidance (mirrors the spec): surface the target band live so the
// "word count that should be used" lives where the author writes, not in a doc.
function lengthHint(words: number): string {
  if (words === 0) return 'aim for 700–1,200 (standard read)'
  if (words < 250) return 'very short'
  if (words <= 500) return 'quick take (250–500)'
  if (words <= 1200) return '✓ standard read (700–1,200)'
  if (words <= 2500) return 'deep dive (1,500–2,500)'
  return 'long — consider splitting into a series'
}

export function ArticleEditor({ initial, onSave, saving }: ArticleEditorProps) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [excerpt, setExcerpt] = useState(initial?.excerpt ?? '')
  const [tags, setTags] = useState((initial?.tags ?? []).join(', '))
  const [body, setBody] = useState(initial?.body_markdown ?? '')

  const wordCount = body.trim() ? body.trim().split(/\s+/).length : 0
  const readMinutes = Math.max(1, Math.round(wordCount / 230))

  return (
    <div className={styles.editor}>
      <div className={styles.fields}>
        <input className={styles.input} placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <input className={styles.input} placeholder="Excerpt" value={excerpt} onChange={(e) => setExcerpt(e.target.value)} />
        <input className={styles.input} placeholder="Tags (comma-separated)" value={tags} onChange={(e) => setTags(e.target.value)} />
      </div>
      <div className={styles.split}>
        <textarea className={styles.textarea} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write Markdown…" />
        <div className={styles.preview}><MarkdownView markdown={body} /></div>
      </div>
      <div className={styles.wordcount}>
        {wordCount} words · ~{readMinutes} min · {lengthHint(wordCount)}
      </div>
      <button
        className={styles.save}
        disabled={saving || !title.trim()}
        onClick={() => onSave({
          title, excerpt, body_markdown: body,
          tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
        })}
      >
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  )
}
