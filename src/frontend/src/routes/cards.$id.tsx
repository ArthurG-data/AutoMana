// src/frontend/src/routes/cards.$id.tsx
import { createFileRoute, Link } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { cardDetailQueryOptions } from '../features/cards/api'
import { CardDetailView } from '../features/cards/components/CardDetailView'
import styles from './cards.$id.module.css'

export const Route = createFileRoute('/cards/$id')({
  loader: ({ params, context: { queryClient } }) =>
    queryClient.ensureQueryData(cardDetailQueryOptions(params.id)),
  component: CardDetailPage,
})

function CardDetailPage() {
  const { id } = Route.useParams()
  const { data: card } = useSuspenseQuery(cardDetailQueryOptions(id))

  const setCode = card.set_code ?? ''
  const cardName = card.card_name ?? ''

  const breadcrumb = (
    <span className={styles.crumb}>
      <Link
        to="/search"
        search={cardName ? { q: cardName } : undefined}
        className={styles.crumbLink}
      >
        SEARCH
      </Link>
      {setCode && (
        <>
          <span className={styles.crumbSep} aria-hidden="true"> › </span>
          <Link
            to="/search"
            search={{ set: setCode }}
            className={styles.crumbLink}
          >
            {setCode.toUpperCase()}
          </Link>
        </>
      )}
    </span>
  )

  return (
    <AppShell active="collection">
      <TopBar title={card.card_name} breadcrumb={breadcrumb} />
      <CardDetailView card={card} />
    </AppShell>
  )
}
