// src/frontend/src/routes/listings_.new.tsx
import { useState, useEffect } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { AppShell } from '../components/layout/AppShell'
import { TopBar } from '../components/layout/TopBar'
import { CardPicker } from '../features/ebay/components/CardPicker'
import {
  ListingFormPanel,
  type ListingFormValues,
} from '../features/ebay/components/ListingFormPanel'
import {
  fetchUserApps,
  createListing,
  type EbayAppSummary,
} from '../features/ebay/api'
import type { CardSummary } from '../features/cards/types'
import styles from './ListingsNew.module.css'

export const Route = createFileRoute('/listings_/new')({
  component: ListingsNewPage,
})

export function ListingsNewPage() {
  const navigate = useNavigate()
  const [isLoadingApps, setIsLoadingApps] = useState(true)
  const [productionApps, setProductionApps] = useState<EbayAppSummary[]>([])
  const [selectedCard, setSelectedCard] = useState<CardSummary | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const apps = await fetchUserApps()
        if (!cancelled) {
          setProductionApps(apps.filter((a) => a.environment === 'PRODUCTION'))
        }
      } catch {
        // leave apps empty — form will have no app choices
      } finally {
        if (!cancelled) setIsLoadingApps(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const derivedTitle = selectedCard
    ? `${selectedCard.card_name} ${selectedCard.set_code.toUpperCase()} NM MTG`
    : ''

  const initialValues: Partial<ListingFormValues> = {
    title: derivedTitle,
    conditionId: 3000,
  }

  async function handleSave(values: ListingFormValues, appCode: string) {
    setIsSaving(true)
    setSaveError(null)
    try {
      await createListing(appCode, {
        title: values.title,
        startPrice: { currency: 'AUD', value: values.price },
        quantity: values.quantity,
        conditionID: values.conditionId,
        ...(values.description ? { description: values.description } : {}),
      })
      navigate({ to: '/listings' })
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to create listing')
    } finally {
      setIsSaving(false)
    }
  }

  function handleCancel() {
    navigate({ to: '/listings' })
  }

  if (isLoadingApps) {
    return (
      <AppShell active="listings">
        <TopBar title="New listing" />
        <div data-testid="loading" className={styles.loading}>
          Loading…
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell active="listings">
      <TopBar title="New listing" breadcrumb="LISTINGS › NEW" />
      <div className={styles.page}>
        <div className={styles.split}>
          <CardPicker
            onSelect={setSelectedCard}
            selectedId={selectedCard?.card_version_id}
          />
          <div className={styles.formWrapper}>
            <ListingFormPanel
              key={selectedCard?.card_version_id ?? 'no-card'}
              mode="create"
              initialValues={initialValues}
              availableApps={productionApps}
              onSave={handleSave}
              onCancel={handleCancel}
              isSaving={isSaving}
              error={saveError}
            />
          </div>
        </div>
      </div>
    </AppShell>
  )
}
