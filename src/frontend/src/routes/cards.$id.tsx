// src/frontend/src/routes/cards.$id.tsx
import { createFileRoute } from '@tanstack/react-router'
import { useSuspenseQuery } from '@tanstack/react-query'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { cardDetailQueryOptions } from '../features/cards/api'
import { CardDetailView } from '../features/cards/components/CardDetailView'

export const Route = createFileRoute('/cards/$id')({
  loader: ({ params, context: { queryClient } }) =>
    queryClient.ensureQueryData(cardDetailQueryOptions(params.id)),
  component: CardDetailPage,
})

function CardDetailPage() {
  const { id } = Route.useParams()
  const { data: card } = useSuspenseQuery(cardDetailQueryOptions(id))

  return (
    <AppShell active="collection">
      <TopBar
        title={card.name}
        breadcrumb={`SEARCH › ${card.set} › ${card.name.toUpperCase()}`}
      />
      <CardDetailView card={card} />
    </AppShell>
  )
}
