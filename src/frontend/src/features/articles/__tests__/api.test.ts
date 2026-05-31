import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as client from '../../../lib/apiClient'
import { listPublicArticles, getPublicArticle, createArticle } from '../api'

describe('articles api', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('listPublicArticles calls the public list endpoint', async () => {
    const spy = vi.spyOn(client, 'apiClient').mockResolvedValue([])
    await listPublicArticles({ tag: 'spec' })
    expect(spy).toHaveBeenCalledWith('/content/articles/?tag=spec')
  })

  it('getPublicArticle fetches by slug', async () => {
    const spy = vi.spyOn(client, 'apiClient').mockResolvedValue({ slug: 'x' })
    await getPublicArticle('x')
    expect(spy).toHaveBeenCalledWith('/content/articles/x')
  })

  it('createArticle POSTs to the admin endpoint', async () => {
    const spy = vi.spyOn(client, 'apiClient').mockResolvedValue({ slug: 'x' })
    await createArticle({ title: 'Hi' })
    expect(spy).toHaveBeenCalledWith('/content/articles/admin/', {
      method: 'POST',
      body: JSON.stringify({ title: 'Hi' }),
    })
  })
})
