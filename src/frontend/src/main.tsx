// src/frontend/src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister'
import { routeTree } from './routeTree.gen'
import { queryClient } from './lib/queryClient'
import './styles/global.css'

const persister = createSyncStoragePersister({
  storage: window.localStorage,
  key: 'automana-rq-cache',
})

const router = createRouter({
  routeTree,
  context: { queryClient },
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

async function enableMocking() {
  // Enable MSW in dev unless explicitly disabled via VITE_DISABLE_MSW=true
  if (import.meta.env.DEV && import.meta.env.VITE_DISABLE_MSW !== 'true') {
    const { worker } = await import('./mocks/browser')
    return worker.start({ onUnhandledRequest: 'bypass' })
  }
}

enableMocking().then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <PersistQueryClientProvider
        client={queryClient}
        persistOptions={{ persister, maxAge: 30 * 60 * 1000 }}
      >
        <RouterProvider router={router} />
      </PersistQueryClientProvider>
    </React.StrictMode>
  )
})
