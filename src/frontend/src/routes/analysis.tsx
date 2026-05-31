import { createFileRoute } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { publicArticlesQueryOptions } from '../features/articles/api'
import { ArticleGrid } from '../features/articles/components/ArticleGrid'
import styles from './analysis.module.css'

export const Route = createFileRoute('/analysis')({
  loader: ({ context: { queryClient } }) =>
    queryClient.ensureQueryData(publicArticlesQueryOptions()),
  component: AnalysisHubPage,
})

function AnalysisHubPage() {
  const { data: articles } = useSuspenseQuery(publicArticlesQueryOptions())
  return (
    <AppShell active="analysis">
      <TopBar title="Analysis" />
      <div className={styles.page}>
        <p className={styles.lede}>Market reads, specs, and arbitrage notes.</p>
        <ArticleGrid articles={articles} />
      </div>
    </AppShell>
  )
}
