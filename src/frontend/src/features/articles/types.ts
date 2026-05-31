export interface ArticleSummary {
  article_id: string
  slug: string
  title: string
  excerpt: string
  cover_image_url: string | null
  status: 'draft' | 'published'
  tags: string[]
  read_minutes: number
  published_at: string | null
  created_at: string
  updated_at: string
}

export interface Article extends ArticleSummary {
  body_markdown: string
  author_id: string | null
}

export interface ArticleCreate {
  title: string
  excerpt?: string
  body_markdown?: string
  cover_image_url?: string | null
  tags?: string[]
}

export type ArticleUpdate = Partial<ArticleCreate>
