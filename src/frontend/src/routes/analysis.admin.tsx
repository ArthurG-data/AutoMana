import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { listAdminArticles, createArticle, publishArticle } from '../features/articles/api'
import styles from './analysis.module.css'

export const Route = createFileRoute('/analysis/admin')({
  component: AdminListPage,
})

function AdminListPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: articles = [] } = useQuery({ queryKey: ['articles', 'admin'], queryFn: listAdminArticles })
  const create = useMutation({
    mutationFn: () => createArticle({ title: 'Untitled draft' }),
    onSuccess: (a) => navigate({ to: '/analysis/admin/$id', params: { id: a.article_id } }),
  })
  const publish = useMutation({
    mutationFn: ({ id, published }: { id: string; published: boolean }) => publishArticle(id, published),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['articles'] }),
  })
  return (
    <AppShell active="analysis">
      <TopBar title="Analysis — Admin" />
      <div className={styles.page}>
        <button className={styles.lede} onClick={() => create.mutate()}>+ New article</button>
        <ul>
          {articles.map((a) => (
            <li key={a.article_id} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '8px 0' }}>
              <Link to="/analysis/admin/$id" params={{ id: a.article_id }}>{a.title}</Link>
              <span style={{ fontSize: 12, color: '#888' }}>{a.status}</span>
              <button onClick={() => publish.mutate({ id: a.article_id, published: a.status !== 'published' })}>
                {a.status === 'published' ? 'Unpublish' : 'Publish'}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </AppShell>
  )
}
