/**
 * IngredientSearchField - Autocomplete name field backed by the ingredients DB.
 *
 * Drop-in replacement for the plain text "name" field in EntityFormModal.
 * Searches /api/ingredients/search on keystroke, shows suggestions,
 * and auto-fills ingredient_id + category + unit via updateFormData.
 * Still allows free-text entry for custom items.
 */

import { useState, useEffect, useRef } from 'react'
import { apiRequest } from '../../../lib/api'
import type { FieldRendererProps } from '../FieldRenderer'

interface IngredientSuggestion {
  id: string
  name: string
  category: string | null
  default_unit: string | null
}

export function IngredientSearchField({
  name,
  label,
  value,
  onChange,
  required,
  error,
  disabled,
  updateFormData,
}: FieldRendererProps) {
  const [searchQuery, setSearchQuery] = useState(value || '')
  const [suggestions, setSuggestions] = useState<IngredientSuggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Sync external value changes (e.g. edit mode initialData)
  useEffect(() => {
    if (value && value !== searchQuery) {
      setSearchQuery(value)
    }
  }, [value])

  // Debounced search
  useEffect(() => {
    if (!searchQuery || searchQuery.length < 2) {
      setSuggestions([])
      return
    }

    const timer = setTimeout(async () => {
      try {
        const result = await apiRequest(
          `/api/ingredients/search?q=${encodeURIComponent(searchQuery)}`
        )
        setSuggestions((result.data || []).slice(0, 10))
      } catch (err) {
        console.error('Ingredient search failed:', err)
        setSuggestions([])
      }
    }, 200)

    return () => clearTimeout(timer)
  }, [searchQuery])

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = (suggestion: IngredientSuggestion) => {
    setSearchQuery(suggestion.name)
    onChange(suggestion.name)
    setShowSuggestions(false)

    if (updateFormData) {
      const updates: Record<string, any> = {
        ingredient_id: suggestion.id,
        category: suggestion.category,
      }
      // Only auto-fill unit if not already set
      if (suggestion.default_unit) {
        updates.unit = suggestion.default_unit
      }
      updateFormData(updates)
    }
  }

  const handleBlur = () => {
    // Sync free-text to form value
    if (searchQuery !== value) {
      onChange(searchQuery)
      // Clear ingredient link if user typed something different
      if (updateFormData) {
        updateFormData({ ingredient_id: null })
      }
    }
    // Delay hiding to allow click on suggestion
    setTimeout(() => setShowSuggestions(false), 150)
  }

  const formatLabel = (str: string) =>
    str
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
        {label || formatLabel(name)}
        {required && <span className="text-[var(--color-error)] ml-1">*</span>}
      </label>

      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value)
            setShowSuggestions(true)
          }}
          onFocus={() => searchQuery.length >= 2 && setShowSuggestions(true)}
          onBlur={handleBlur}
          placeholder="Search ingredients..."
          disabled={disabled}
          className={`
            w-full px-3 py-2 rounded-[var(--radius-md)]
            bg-[var(--color-bg-secondary)] border border-[var(--color-border)]
            text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]
            focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]
            disabled:opacity-50 disabled:cursor-not-allowed
            ${error ? 'border-[var(--color-error)]' : ''}
          `}
        />

        {showSuggestions && suggestions.length > 0 && (
          <div
            ref={dropdownRef}
            className="absolute z-50 w-full mt-1 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-lg max-h-48 overflow-y-auto"
          >
            {suggestions.map((sug) => (
              <button
                key={sug.id}
                type="button"
                onClick={() => handleSelect(sug)}
                className="w-full px-3 py-2 text-left text-sm hover:bg-[var(--color-bg-tertiary)] transition-colors flex items-center justify-between"
              >
                <span className="text-[var(--color-text-primary)]">{sug.name}</span>
                {sug.category && (
                  <span className="text-xs text-[var(--color-text-muted)] capitalize">
                    {sug.category}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-xs text-[var(--color-error)]">{error}</p>}
    </div>
  )
}
