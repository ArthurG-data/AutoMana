import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchEntriesPage, PAGE_SIZE } from '../api'
import type { CollectionEntry } from '../api'

interface UseInfiniteEntriesResult {
  allEntries: CollectionEntry[]
  isFetchingMore: boolean
  hasMore: boolean
  fetchNextPage: () => Promise<void>
  removeEntry: (itemId: string) => void
  sentinelRef: React.RefObject<HTMLDivElement>
}

export function useInfiniteEntries(collectionId: string | null): UseInfiniteEntriesResult {
  const [allEntries, setAllEntries] = useState<CollectionEntry[]>([])
  const [isFetchingMore, setIsFetchingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const offsetRef = useRef(0)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const isFetchingRef = useRef(false)

  // Reset and load first page when collectionId changes
  useEffect(() => {
    if (!collectionId) {
      setAllEntries([])
      setHasMore(false)
      return
    }
    let cancelled = false
    offsetRef.current = 0
    setAllEntries([])
    setHasMore(true)
    setIsFetchingMore(true)
    fetchEntriesPage(collectionId, 0, PAGE_SIZE).then((page) => {
      if (cancelled) return
      setAllEntries(page)
      offsetRef.current = page.length
      setHasMore(page.length === PAGE_SIZE)
      setIsFetchingMore(false)
    })
    return () => { cancelled = true }
  }, [collectionId])

  const fetchNextPage = useCallback(async () => {
    if (!collectionId || isFetchingRef.current || !hasMore) return
    isFetchingRef.current = true
    setIsFetchingMore(true)
    const page = await fetchEntriesPage(collectionId, offsetRef.current, PAGE_SIZE)
    setAllEntries((prev) => [...prev, ...page])
    offsetRef.current += page.length
    setHasMore(page.length === PAGE_SIZE)
    isFetchingRef.current = false
    setIsFetchingMore(false)
  }, [collectionId, hasMore])

  // Intersection Observer wires the sentinel to fetchNextPage
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) fetchNextPage()
      },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [fetchNextPage])

  const removeEntry = useCallback((itemId: string) => {
    setAllEntries((prev) => prev.filter((e) => e.item_id !== itemId))
  }, [])

  return { allEntries, isFetchingMore, hasMore, fetchNextPage, removeEntry, sentinelRef }
}
