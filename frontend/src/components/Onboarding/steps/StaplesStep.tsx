import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../../lib/api'

interface StaplesStepProps {
  onNext: () => void
  onBack: () => void
}

interface Ingredient {
  id: string
  name: string
  tier: number
  cuisine_match?: boolean
}

interface Category {
  id: string
  label: string
  icon: string
  ingredients: Ingredient[]
}

interface StaplesResponse {
  categories: Category[]
  pre_selected_ids: string[]
  cuisine_suggested_ids: string[]
}

export function StaplesStep({ onNext, onBack }: StaplesStepProps) {
  const [categories, setCategories] = useState<Category[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [cuisineSuggested, setCuisineSuggested] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Number of items to show before "Show more"
  const INITIAL_SHOW_COUNT = 8

  useEffect(() => {
    loadStaples()
  }, [])

  const loadStaples = async () => {
    try {
      // First get the user's cuisine selections from state
      const stateData = await apiRequest<{ cuisine_preferences: string[] }>('/api/onboarding/state')
      const cuisines = stateData.cuisine_preferences || []

      // Fetch staples with cuisine context
      const cuisineParam = cuisines.length > 0 ? `?cuisines=${cuisines.join(',')}` : ''
      const data = await apiRequest<StaplesResponse>(`/api/onboarding/staples/options${cuisineParam}`)

      setCategories(data.categories)
      setSelected(new Set(data.pre_selected_ids))
      setCuisineSuggested(new Set(data.cuisine_suggested_ids))

      // Auto-expand categories with tier 1 items
      const autoExpand = new Set<string>()
      data.categories.forEach(cat => {
        if (cat.ingredients.some(i => i.tier === 1)) {
          autoExpand.add(cat.id)
        }
      })
      setExpanded(autoExpand)
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

  const toggleCategory = (categoryId: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(categoryId)) {
        next.delete(categoryId)
      } else {
        next.add(categoryId)
      }
      return next
    })
  }

  const selectAllInCategory = (categoryId: string) => {
    const category = categories.find(c => c.id === categoryId)
    if (!category) return

    setSelected(prev => {
      const next = new Set(prev)
      category.ingredients.forEach(ing => next.add(ing.id))
      return next
    })
  }

  const deselectAllInCategory = (categoryId: string) => {
    const category = categories.find(c => c.id === categoryId)
    if (!category) return

    setSelected(prev => {
      const next = new Set(prev)
      category.ingredients.forEach(ing => next.delete(ing.id))
      return next
    })
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
    // Save empty selection and continue
    apiRequest('/api/onboarding/staples', {
      method: 'POST',
      body: JSON.stringify({ ingredient_ids: [] }),
    }).then(() => onNext()).catch(() => onNext())
  }

  const getCategorySelectedCount = (category: Category) => {
    return category.ingredients.filter(i => selected.has(i.id)).length
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
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          What basics do you always keep stocked?
        </h2>
        <p className="text-[var(--color-text-muted)]">
          Alfred won't ask about these when suggesting recipes. We've pre-selected common staples.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
          {error}
        </div>
      )}

      {/* Category Accordions */}
      <div className="space-y-3">
        {categories.map((category) => {
          const isExpanded = expanded.has(category.id)
          const selectedCount = getCategorySelectedCount(category)
          const visibleIngredients = isExpanded
            ? category.ingredients
            : category.ingredients.slice(0, INITIAL_SHOW_COUNT)
          const hasMore = category.ingredients.length > INITIAL_SHOW_COUNT

          return (
            <div
              key={category.id}
              className="border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--color-bg-secondary)]"
            >
              {/* Category Header */}
              <button
                onClick={() => toggleCategory(category.id)}
                className="w-full px-4 py-3 flex items-center justify-between hover:bg-[var(--color-bg-tertiary)] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xl">{category.icon}</span>
                  <span className="font-medium text-[var(--color-text-primary)]">
                    {category.label}
                  </span>
                  {selectedCount > 0 && (
                    <span className="text-xs px-2 py-0.5 bg-[var(--color-accent-muted)] text-[var(--color-accent)] rounded-full">
                      {selectedCount} selected
                    </span>
                  )}
                </div>
                <motion.span
                  animate={{ rotate: isExpanded ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                  className="text-[var(--color-text-muted)]"
                >
                  ▼
                </motion.span>
              </button>

              {/* Category Content */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <div className="px-4 pb-4">
                      {/* Select All / Deselect All */}
                      <div className="flex gap-3 mb-3 text-xs">
                        <button
                          onClick={() => selectAllInCategory(category.id)}
                          className="text-[var(--color-accent)] hover:underline"
                        >
                          Select all
                        </button>
                        <button
                          onClick={() => deselectAllInCategory(category.id)}
                          className="text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                        >
                          Deselect all
                        </button>
                      </div>

                      {/* Ingredients Grid */}
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {visibleIngredients.map((ingredient) => {
                          const isSelected = selected.has(ingredient.id)
                          const isCuisineMatch = cuisineSuggested.has(ingredient.id)

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
                                    w-4 h-4 rounded border flex items-center justify-center text-xs
                                    ${isSelected
                                      ? 'bg-[var(--color-accent)] border-[var(--color-accent)] text-white'
                                      : 'border-[var(--color-border)]'
                                    }
                                  `}
                                >
                                  {isSelected && '✓'}
                                </span>
                                <span className="text-[var(--color-text-primary)] truncate flex-1">
                                  {ingredient.name}
                                </span>
                                {isCuisineMatch && !isSelected && (
                                  <span className="text-xs text-[var(--color-accent)]" title="Matches your cuisines">
                                    ★
                                  </span>
                                )}
                              </div>
                            </motion.button>
                          )
                        })}
                      </div>

                      {/* Show More */}
                      {hasMore && !isExpanded && (
                        <button
                          onClick={() => toggleCategory(category.id)}
                          className="mt-2 text-sm text-[var(--color-accent)] hover:underline"
                        >
                          Show {category.ingredients.length - INITIAL_SHOW_COUNT} more...
                        </button>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        })}
      </div>

      {/* Selection Counter */}
      <div className="text-center text-sm text-[var(--color-text-muted)]">
        {selected.size} staple{selected.size !== 1 ? 's' : ''} selected
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
