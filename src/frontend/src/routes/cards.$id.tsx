// src/frontend/src/routes/cards.$id.tsx
import { createFileRoute, Link } from '@tanstack/react-router'
import { useSuspenseQuery, useQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { cardDetailQueryOptions, cardVersionsInSetQueryOptions, cardOtherSetsQueryOptions } from '../features/cards/api'
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
  const uniqueCardId = card.unique_card_id

  const { data: versionsInSet } = useQuery({
    ...cardVersionsInSetQueryOptions(
      uniqueCardId ? String(uniqueCardId) : '',
      setCode
    ),
    enabled: !!uniqueCardId && !!setCode,
  })

  const { data: otherSets } = useQuery({
    ...cardOtherSetsQueryOptions(uniqueCardId ? String(uniqueCardId) : ''),
    enabled: !!uniqueCardId,
  })

  // Card-name segment navigates to the search page filtered by the stable
  // unique_card_id of this print — so it shows every printing of the same
  // logical card across sets, not a fuzzy name search.
  const nameSearch = uniqueCardId
    ? { unique_card_id: uniqueCardId }
    : cardName
      ? { q: cardName }
      : undefined

  const breadcrumb = (
    <span className={styles.crumb}>
      <Link
        to="/search"
        search={nameSearch}
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
      {cardName && (
        <>
          <span className={styles.crumbSep} aria-hidden="true"> › </span>
          <Link
            to="/search"
            search={nameSearch}
            className={`${styles.crumbLink} ${styles.crumbCurrent}`}
          >
            {cardName}
          </Link>
        </>
      )}
    </span>
  )

  return (
    <AppShell active="collection">
      <TopBar breadcrumb={breadcrumb} />
      <CardDetailView
        card={card}
        versionsInSet={versionsInSet ?? undefined}
        otherSets={otherSets ?? undefined}
      />
    </AppShell>
  )
}
