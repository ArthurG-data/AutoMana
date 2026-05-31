import { createFileRoute } from '@tanstack/react-router'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { getAdminArticle, updateArticle } from '../features/articles/api'
import { ArticleEditor } from '../features/articles/components/ArticleEditor'

export const Route = createFileRoute('/analysis/admin/$id')({
  component: EditorPage,
})

function EditorPage() {
  const { id } = Route.useParams()
  const qc = useQueryClient()
  const { data: article } = useQuery({ queryKey: ['articles', 'admin', id], queryFn: () => getAdminArticle(id) })
  const save = useMutation({
    mutationFn: (payload: Parameters<typeof updateArticle>[1]) => updateArticle(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['articles'] }),
  })
  return (
    <AppShell active="analysis">
      <TopBar title="Edit article" />
      {article && <ArticleEditor initial={article} saving={save.isPending} onSave={(p) => save.mutate(p)} />}
    </AppShell>
  )
}
