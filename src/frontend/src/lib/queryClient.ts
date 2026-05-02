// src/frontend/src/lib/queryClient.ts
import {
  QueryClient,
  QueryCache,
  MutationCache,
} from '@tanstack/react-query'
import { useAuthStore } from '../store/auth'
import type { ApiError } from './apiClient'

function handle401(err: unknown) {
  if ((err as ApiError).status === 401) {
    useAuthStore.getState().logout()
  }
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handle401 }),
  mutationCache: new MutationCache({ onError: handle401 }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) =>
        (err as ApiError).status !== 401 && count < 2,
    },
  },
})
