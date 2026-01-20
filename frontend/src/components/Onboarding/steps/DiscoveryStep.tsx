import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../../lib/api'

interface DiscoveryStepProps {
  onNext: () => void
  onBack: () => void
}

interface Category {
  id: string
  label: string
}

interface Ingredient {
  id: string
  name: string
  category: string
}

interface Summary {
  total: number
  likes: number
  dislikes: number
  top_likes: { name: string; category: string }[]
  top_dislikes: { name: string; category: string }[]
}

export function DiscoveryStep({ onNext, onBack }: DiscoveryStepProps) {
  const [categories, setCategories] = useState<Category[]>([])
  const [currentCategory, setCurrentCategory] = useState<string | null>(null)
  const [ingredients, setIngredients] = useState<Ingredient[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Track local preferences before submitting
  const [localPrefs, setLocalPrefs] = useState<Record<string, 'like' | 'dislike'>>({})

  useEffect(() => {
    loadCategories()
    loadSummary()
  }, [])

  // If user already has 20+ preferences from Favorites step, they can skip
  const canSkipImmediately = (summary?.total || 0) >= 20

  useEffect(() => {
    if (currentCategory) {
      loadIngredients(currentCategory)
    }
  }, [currentCategory])

  const loadCategories = async () => {
    try {
      const data = await fetch('/api/onboarding/discovery/categories')
      const json = await data.json()
      // API returns {categories: [...]}
      const cats = json.categories || []
      setCategories(cats)
      if (cats.length > 0) {
        setCurrentCategory(cats[0].id)
      }
    } catch (err) {
      setError('Failed to load categories')
    } finally {
      setLoading(false)
    }
  }

  const loadIngredients = async (categoryId: string) => {
    try {
      const data = await apiRequest<{ ingredients: Ingredient[] }>(
        `/api/onboarding/discovery/ingredients?category=${categoryId}`
      )
      setIngredients(data.ingredients || [])
    } catch (err) {
      console.error('Failed to load ingredients:', err)
    }
  }

  const loadSummary = async () => {
    try {
      const data = await apiRequest<Summary>('/api/onboarding/discovery/summary')
      setSummary(data)
    } catch (err) {
      console.error('Failed to load summary:', err)
    }
  }

  const handlePreference = async (ingredientId: string, score: 1 | -1) => {
    // Optimistic update
    setLocalPrefs(prev => ({
      ...prev,
      [ingredientId]: score === 1 ? 'like' : 'dislike'
    }))

    try {
      await apiRequest('/api/onboarding/discovery/preference', {
        method: 'POST',
        body: JSON.stringify({
          ingredient_id: ingredientId,
          preference: score === 1 ? 'like' : 'dislike',
        }),
      })
      // Refresh summary
      loadSummary()
    } catch (err) {
      // Revert on error
      setLocalPrefs(prev => {
        const next = { ...prev }
        delete next[ingredientId]
        return next
      })
      console.error('Failed to save preference:', err)
    }
  }

  const handleComplete = async () => {
    setSaving(true)
    setError('')

    try {
      await apiRequest('/api/onboarding/discovery/complete', {
        method: 'POST',
      })
      onNext()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete')
      setSaving(false)
    }
  }

  const getPreference = (id: string): 'like' | 'dislike' | null => {
    if (localPrefs[id]) return localPrefs[id]
    // Note: Summary doesn't contain IDs, only names. Local state tracks IDs.
    return null
  }

  const totalPrefs = summary?.total || 0

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          What do you love (or avoid)?
        </h2>
        <p className="text-[var(--color-text-muted)]">
          Tap 👍 for ingredients you like, 👎 for ones you'd rather skip.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
          {error}
        </div>
      )}

      {/* Already have enough - can skip */}
      {canSkipImmediately && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-4 bg-[var(--color-success-muted)] border border-[var(--color-success)] rounded-[var(--radius-lg)]"
        >
          <p className="text-[var(--color-success)] font-medium mb-2">
            ✓ You've already added {totalPrefs} preferences from your favorites!
          </p>
          <p className="text-[var(--color-text-muted)] text-sm mb-3">
            You can continue to fine-tune, or skip ahead.
          </p>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleComplete}
            disabled={saving}
            className="px-6 py-2 bg-[var(--color-success)] text-white font-medium rounded-[var(--radius-md)] transition-colors"
          >
            {saving ? 'Finishing...' : 'Skip & Finish Setup'}
          </motion.button>
        </motion.div>
      )}

      {/* Progress */}
      <div className="flex items-center gap-4 p-4 bg-[var(--color-bg-secondary)] rounded-[var(--radius-lg)]">
        <div className="flex-1">
          <div className="h-2 bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-[var(--color-accent)]"
              initial={{ width: 0 }}
              animate={{ width: `${Math.min((totalPrefs / 20) * 100, 100)}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>
        <div className="text-sm text-[var(--color-text-secondary)] whitespace-nowrap">
          {totalPrefs} / 20
        </div>
      </div>

      {/* Category Tabs */}
      <div className="flex overflow-x-auto gap-2 pb-2 -mx-2 px-2">
        {categories.map(cat => (
          <button
            key={cat.id}
            onClick={() => setCurrentCategory(cat.id)}
            className={`
              px-4 py-2 rounded-full text-sm whitespace-nowrap transition-colors
              ${currentCategory === cat.id
                ? 'bg-[var(--color-accent)] text-[var(--color-text-inverse)]'
                : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]'
              }
            `}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Ingredients Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <AnimatePresence mode="popLayout">
          {ingredients.map((ing, idx) => {
            const pref = getPreference(ing.id)
            return (
              <motion.div
                key={ing.id}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ delay: idx * 0.03 }}
                className={`
                  flex items-center justify-between p-4 rounded-[var(--radius-lg)] border transition-colors
                  ${pref === 'like' 
                    ? 'bg-[var(--color-success-muted)] border-[var(--color-success)]' 
                    : pref === 'dislike'
                      ? 'bg-[var(--color-error-muted)] border-[var(--color-error)]'
                      : 'bg-[var(--color-bg-secondary)] border-[var(--color-border)]'
                  }
                `}
              >
                <span className="font-medium text-[var(--color-text-primary)]">
                  {ing.name}
                </span>
                <div className="flex gap-2">
                  <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={() => handlePreference(ing.id, 1)}
                    className={`
                      w-10 h-10 rounded-full flex items-center justify-center text-lg transition-all
                      ${pref === 'like'
                        ? 'bg-[var(--color-success)] text-white'
                        : 'bg-[var(--color-bg-tertiary)] hover:bg-[var(--color-success-muted)]'
                      }
                    `}
                  >
                    👍
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={() => handlePreference(ing.id, -1)}
                    className={`
                      w-10 h-10 rounded-full flex items-center justify-center text-lg transition-all
                      ${pref === 'dislike'
                        ? 'bg-[var(--color-error)] text-white'
                        : 'bg-[var(--color-bg-tertiary)] hover:bg-[var(--color-error-muted)]'
                      }
                    `}
                  >
                    👎
                  </motion.button>
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>

      {/* Ready to Continue */}
      {totalPrefs >= 20 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-4 bg-[var(--color-accent-muted)] border border-[var(--color-accent)] rounded-[var(--radius-lg)] text-center"
        >
          <p className="text-[var(--color-accent)] font-medium">
            Great! You've rated {totalPrefs} ingredients. Ready to continue?
          </p>
        </motion.div>
      )}

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
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleComplete}
          disabled={saving}
          className={`
            px-8 py-3 font-semibold rounded-[var(--radius-lg)] transition-colors disabled:opacity-50
            ${totalPrefs >= 20
              ? 'bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)]'
              : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]'
            }
          `}
        >
          {saving ? 'Finishing...' : totalPrefs >= 20 ? 'Finish Setup' : 'Skip for now'}
        </motion.button>
      </div>
    </div>
  )
}
