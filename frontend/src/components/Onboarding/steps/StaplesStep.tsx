import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../../lib/api'

interface StaplesStepProps {
  onNext: () => void
  onBack: () => void
}

interface Ingredient {
  id: string
  name: string
  default_unit?: string | null
  parent_category?: string | null
  cuisine_match?: boolean
}

interface StaplesResponse {
  essentials: Ingredient[]
  pre_selected_ids: string[]
  cuisine_suggested_ids: string[]
}

interface SearchResult {
  id: string
  name: string
  category?: string | null
  default_unit?: string | null
  aliases?: string[] | null
}

const CATEGORY_LABELS: Record<string, string> = {
  pantry: 'Pantry Essentials',
  spices: 'Spices & Seasonings',
  grains: 'Grains & Pasta',
  baking: 'Baking',
  dairy: 'Dairy & Eggs',
}

// Display order for categories
const CATEGORY_ORDER = ['pantry', 'spices', 'grains', 'dairy', 'baking']

function groupByCategory(ingredients: Ingredient[]): Record<string, Ingredient[]> {
  const groups: Record<string, Ingredient[]> = {}
  for (const ing of ingredients) {
    const cat = ing.parent_category || 'other'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(ing)
  }
  // Sort by defined order, unknowns at end
  const sorted: Record<string, Ingredient[]> = {}
  for (const cat of CATEGORY_ORDER) {
    if (groups[cat]) sorted[cat] = groups[cat]
  }
  for (const cat of Object.keys(groups)) {
    if (!sorted[cat]) sorted[cat] = groups[cat]
  }
  return sorted
}

export function StaplesStep({ onNext, onBack }: StaplesStepProps) {
  const [essentials, setEssentials] = useState<Ingredient[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [additions, setAdditions] = useState<Ingredient[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    loadStaples()
  }, [])

  const loadStaples = async () => {
    try {
      const stateData = await apiRequest<{ cuisine_preferences: string[] }>('/api/onboarding/state')
      const cuisines = stateData.cuisine_preferences || []

      const cuisineParam = cuisines.length > 0 ? `?cuisines=${cuisines.join(',')}` : ''
      const data = await apiRequest<StaplesResponse>(`/api/onboarding/staples/options${cuisineParam}`)

      setEssentials(data.essentials)
      // Start with nothing selected — user taps to add what they keep stocked
      setSelected(new Set())
    } catch (err) {
      console.error('Failed to load staples:', err)
      setError('Failed to load staples')
    } finally {
      setLoading(false)
    }
  }

  const toggleIngredient = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const removeAddition = (id: string) => {
    setAdditions(prev => prev.filter(a => a.id !== id))
    setSelected(prev => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }

  // Debounced search
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value)

    if (searchTimeout.current) {
      clearTimeout(searchTimeout.current)
    }

    if (value.trim().length < 2) {
      setSearchResults([])
      return
    }

    searchTimeout.current = setTimeout(async () => {
      setSearching(true)
      try {
        const data = await apiRequest<{ data: SearchResult[] }>(
          `/api/ingredients/search?q=${encodeURIComponent(value.trim())}`
        )
        // Filter out items already in essentials or additions
        const essentialIds = new Set(essentials.map(e => e.id))
        const additionIds = new Set(additions.map(a => a.id))
        const filtered = (data.data || []).filter(
          r => !essentialIds.has(r.id) && !additionIds.has(r.id)
        )
        setSearchResults(filtered.slice(0, 10))
      } catch (err) {
        console.error('Search failed:', err)
      } finally {
        setSearching(false)
      }
    }, 200)
  }, [essentials, additions])

  const addFromSearch = (result: SearchResult) => {
    const ingredient: Ingredient = {
      id: result.id,
      name: result.name,
      default_unit: result.default_unit,
    }
    setAdditions(prev => [...prev, ingredient])
    setSelected(prev => new Set(prev).add(result.id))
    setSearchResults(prev => prev.filter(r => r.id !== result.id))
    setSearchQuery('')
  }

  const handleSubmit = async () => {
    setSaving(true)
    setError('')

    try {
      await apiRequest('/api/onboarding/staples', {
        method: 'POST',
        body: JSON.stringify({
          ingredient_ids: Array.from(selected),
        }),
      })
      onNext()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
      setSaving(false)
    }
  }

  const handleSkip = () => {
    apiRequest('/api/onboarding/staples', {
      method: 'POST',
      body: JSON.stringify({ ingredient_ids: [] }),
    }).then(() => onNext()).catch(() => onNext())
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[var(--color-text-secondary)]">Loading staples...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          What do you always keep stocked?
        </h2>
        <p className="text-[var(--color-text-muted)]">
          Tap the items you always keep stocked. We'll add them to your pantry so Alfred knows what you have.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
          {error}
        </div>
      )}

      {/* Essentials Checklist — grouped by category */}
      {Object.entries(groupByCategory(essentials)).map(([category, items]) => (
        <div key={category} className="space-y-2">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)] uppercase tracking-wide">
            {CATEGORY_LABELS[category] || category}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {items.map((ingredient) => {
              const isSelected = selected.has(ingredient.id)

              return (
                <motion.button
                  key={ingredient.id}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => toggleIngredient(ingredient.id)}
                  className={`
                    px-3 py-2 rounded-[var(--radius-md)] border text-left text-sm transition-all
                    ${isSelected
                      ? 'bg-[var(--color-accent-muted)] border-[var(--color-accent)]'
                      : 'bg-[var(--color-bg-primary)] border-[var(--color-border)] hover:border-[var(--color-text-muted)]'
                    }
                  `}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`
                        w-4 h-4 rounded border flex items-center justify-center text-xs flex-shrink-0
                        ${isSelected
                          ? 'bg-[var(--color-accent)] border-[var(--color-accent)] text-white'
                          : 'border-[var(--color-border)]'
                        }
                      `}
                    >
                      {isSelected && '✓'}
                    </span>
                    <span className="text-[var(--color-text-primary)] truncate">
                      {ingredient.name}
                    </span>
                    {ingredient.cuisine_match && (
                      <span className="text-xs text-[var(--color-accent)] flex-shrink-0" title="Matches your cuisines">
                        ★
                      </span>
                    )}
                  </div>
                </motion.button>
              )
            })}
          </div>
        </div>
      ))}

      {/* Your Additions (from search) */}
      <AnimatePresence>
        {additions.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
          >
            <div className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">
              Your additions
            </div>
            <div className="flex flex-wrap gap-2">
              {additions.map((item) => (
                <motion.span
                  key={item.id}
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0.8, opacity: 0 }}
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-[var(--color-accent-muted)] border border-[var(--color-accent)] rounded-full text-sm text-[var(--color-text-primary)]"
                >
                  {item.name}
                  <button
                    onClick={() => removeAddition(item.id)}
                    className="ml-1 text-[var(--color-text-muted)] hover:text-[var(--color-error)] text-xs"
                    aria-label={`Remove ${item.name}`}
                  >
                    ×
                  </button>
                </motion.span>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Search Bar */}
      <div className="relative">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Search for more ingredients..."
          className="w-full px-4 py-3 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-lg)] text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)] transition-colors"
        />
        {searching && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--color-text-muted)]">
            ...
          </div>
        )}

        {/* Search Results Dropdown */}
        <AnimatePresence>
          {searchResults.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="absolute z-10 mt-1 w-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-lg overflow-hidden"
            >
              {searchResults.map((result) => (
                <button
                  key={result.id}
                  onClick={() => addFromSearch(result)}
                  className="w-full px-4 py-2.5 text-left text-sm hover:bg-[var(--color-bg-tertiary)] transition-colors flex items-center justify-between"
                >
                  <span className="text-[var(--color-text-primary)]">{result.name}</span>
                  {result.category && (
                    <span className="text-xs text-[var(--color-text-muted)]">{result.category}</span>
                  )}
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Selection Counter */}
      <div className="text-center text-sm text-[var(--color-text-muted)]">
        {selected.size} item{selected.size !== 1 ? 's' : ''} selected
      </div>

      {/* Buttons */}
      <div className="pt-4 flex justify-between">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onBack}
          className="px-6 py-3 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
        >
          ← Back
        </motion.button>
        <div className="flex gap-3">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleSkip}
            className="px-6 py-3 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            Skip
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleSubmit}
            disabled={saving}
            className="px-8 py-3 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-semibold rounded-[var(--radius-lg)] transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Continue'}
          </motion.button>
        </div>
      </div>
    </div>
  )
}
