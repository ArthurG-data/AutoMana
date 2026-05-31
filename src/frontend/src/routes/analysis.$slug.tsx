import { createFileRoute, Link } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { publicArticleQueryOptions } from '../features/articles/api'
import { MarkdownView } from '../features/articles/components/MarkdownView'
import styles from './analysis.module.css'

export const Route = createFileRoute('/analysis/$slug')({
  loader: ({ params, context: { queryClient } }) =>
    queryClient.ensureQueryData(publicArticleQueryOptions(params.slug)),
  component: ArticleReadingPage,
})

function ArticleReadingPage() {
  const { slug } = Route.useParams()
  const { data: article } = useSuspenseQuery(publicArticleQueryOptions(slug))
  return (
    <AppShell active="analysis">
      <TopBar title="Analysis" />
      <article className={styles.reading}>
        {article.tags[0] && <div className={styles.kicker}>{article.tags[0]}</div>}
        <h1 className={styles.readTitle}>{article.title}</h1>
        <div className={styles.readMeta}>
          {article.published_at ? new Date(article.published_at).toLocaleDateString() : 'Draft'} · {article.read_minutes} min read
        </div>
        <MarkdownView markdown={article.body_markdown} />
        <p style={{ marginTop: 40 }}><Link to="/analysis">← All analysis</Link></p>
      </article>
    </AppShell>
  )
}
