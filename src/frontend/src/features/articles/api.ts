import { queryOptions } from '@tanstack/react-query'
import { apiClient } from '../../lib/apiClient'
import type { Article, ArticleSummary, ArticleCreate, ArticleUpdate } from './types'

export async function listPublicArticles(params: { tag?: string } = {}): Promise<ArticleSummary[]> {
  const qs = new URLSearchParams()
  if (params.tag) qs.set('tag', params.tag)
  const suffix = qs.toString() ? `?${qs}` : ''
  return apiClient<ArticleSummary[]>(`/content/articles/${suffix}`)
}

export async function getPublicArticle(slug: string): Promise<Article> {
  return apiClient<Article>(`/content/articles/${slug}`)
}

export async function listAdminArticles(): Promise<ArticleSummary[]> {
  return apiClient<ArticleSummary[]>('/content/articles/admin/')
}

export async function getAdminArticle(id: string): Promise<Article> {
  return apiClient<Article>(`/content/articles/admin/${id}`)
}

export async function createArticle(payload: ArticleCreate): Promise<Article> {
  return apiClient<Article>('/content/articles/admin/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateArticle(id: string, payload: ArticleUpdate): Promise<Article> {
  return apiClient<Article>(`/content/articles/admin/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function publishArticle(id: string, published: boolean): Promise<Article> {
  return apiClient<Article>(`/content/articles/admin/${id}/publish?published=${published}`, {
    method: 'POST',
  })
}

export function publicArticlesQueryOptions(tag?: string) {
  return queryOptions({
    queryKey: ['articles', 'public', tag ?? null],
    queryFn: () => listPublicArticles({ tag }),
  })
}

export function publicArticleQueryOptions(slug: string) {
  return queryOptions({
    queryKey: ['articles', 'public', 'detail', slug],
    queryFn: () => getPublicArticle(slug),
  })
}
