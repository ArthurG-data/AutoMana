// src/frontend/src/features/cards/components/SearchBarWithSuggestions.tsx
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Icon } from '../../../components/design-system/Icon'
import { SuggestionsDropdown } from '../../../components/design-system/SuggestionsDropdown'
import { cardSuggestQueryOptions } from '../api'
import type { CardSuggestion } from '../types'
import styles from './SearchBarWithSuggestions.module.css'

const MIN_CHARS = 2

export function SearchBarWithSuggestions() {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [showDropdown, setShowDropdown] = useState(false)
  const navigate = useNavigate()
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Query suggestions only if we have enough characters
  const shouldFetch = query.trim().length >= MIN_CHARS
  const { data, isLoading } = useQuery({
    ...cardSuggestQueryOptions({ q: query.trim(), limit: 10 }),
    enabled: shouldFetch,
  })

  const suggestions = data?.suggestions ?? []

  // Reset selected index when suggestions change
  useEffect(() => {
    setSelectedIndex(0)
  }, [suggestions])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setQuery(value)
    setShowDropdown(true)

    // Clear previous debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    // Only show dropdown if we have text
    if (value.trim().length >= MIN_CHARS) {
      setShowDropdown(true)
    } else {
      setShowDropdown(false)
    }
  }

  const handleSelectSuggestion = (suggestion: CardSuggestion) => {
    navigate({ to: '/search', search: { q: suggestion.card_name } })
    setShowDropdown(false)
    setQuery('')
  }

  const handleSearch = (searchQuery: string) => {
    navigate({ to: '/search', search: { q: searchQuery.trim() } })
    setShowDropdown(false)
    setQuery('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex((prev) => (prev + 1) % suggestions.length)
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex((prev) => (prev - 1 + suggestions.length) % suggestions.length)
        break
      case 'Enter':
        e.preventDefault()
        if (showDropdown && suggestions.length > 0) {
          handleSelectSuggestion(suggestions[selectedIndex])
        } else if (query.trim()) {
          handleSearch(query)
        }
        break
      case 'Escape':
        setShowDropdown(false)
        break
    }
  }

  const handleInputBlur = () => {
    // Delay closing to allow click on dropdown to register
    debounceTimerRef.current = setTimeout(() => setShowDropdown(false), 200)
  }

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [])

  return (
    <div className={styles.container}>
      <form
        className={styles.searchBar}
        onSubmit={(e) => {
          e.preventDefault()
          if (query.trim()) {
            handleSearch(query)
          }
        }}
      >
        <Icon kind="search" size={20} color="var(--hd-accent)" strokeWidth={1.6} />
        <input
          ref={inputRef}
          className={styles.input}
          type="text"
          placeholder="Search any card by name, set, or artist…"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onBlur={handleInputBlur}
          onFocus={() => query.trim().length >= MIN_CHARS && setShowDropdown(true)}
          aria-label="Search cards"
        />
      </form>
      <SuggestionsDropdown
        suggestions={suggestions}
        selectedIndex={selectedIndex}
        onSelect={handleSelectSuggestion}
        isLoading={isLoading && shouldFetch}
        isOpen={showDropdown && shouldFetch}
      />
    </div>
  )
}
