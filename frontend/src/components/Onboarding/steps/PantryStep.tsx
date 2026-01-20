import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../../lib/api'

interface PantryStepProps {
  onNext: () => void
  onBack: () => void
}

interface Ingredient {
  id: string
  name: string
  category: string
  inPantry?: boolean  // Track if user has this in their pantry
}

export function PantryStep({ onNext, onBack }: PantryStepProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Ingredient[]>([])
  const [selected, setSelected] = useState<Ingredient[]>([])
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [showPantryNudge, setShowPantryNudge] = useState(false)

  // Debounced search
  const search = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([])
      return
    }

    setSearching(true)
    try {
      const data = await fetch(`/api/onboarding/pantry/search?q=${encodeURIComponent(q)}`)
      const json = await data.json()
      // API returns {results: [...]}
      const ingredients = json.results || []
      // Filter out already selected items
      const filtered = ingredients.filter((r: Ingredient) => !selected.some(s => s.id === r.id))
      setResults(filtered)
    } catch (err) {
      console.error('Search failed:', err)
    } finally {
      setSearching(false)
    }
  }, [selected])

  const handleQueryChange = (value: string) => {
    setQuery(value)
    // Simple debounce
    const timeoutId = setTimeout(() => search(value), 200)
    return () => clearTimeout(timeoutId)
  }

  const addItem = (item: Ingredient) => {
    // In pantry nudge mode, new items are both liked AND in pantry
    // Otherwise, just liked (not in pantry yet)
    setSelected(prev => [...prev, { ...item, inPantry: showPantryNudge }])
    setResults([])  // Collapse dropdown
    setQuery('')
  }

  const removeItem = (id: string) => {
    setSelected(prev => prev.filter(i => i.id !== id))
  }

  const togglePantry = (id: string) => {
    setSelected(prev => prev.map(i => 
      i.id === id ? { ...i, inPantry: !i.inPantry } : i
    ))
  }

  const handleSubmit = async () => {
    // If user has items but hasn't seen pantry nudge, show it first
    if (selected.length >= 3 && !showPantryNudge) {
      setShowPantryNudge(true)
      return
    }

    setSaving(true)
    setError('')

    try {
      // Send both liked ingredients and which ones are in pantry
      await apiRequest('/api/onboarding/pantry', {
        method: 'POST',
        body: JSON.stringify({
          items: selected.map(s => ({ 
            name: s.name, 
            category: s.category,
            in_pantry: s.inPantry || false,
          })),
        }),
      })
      onNext()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
      setSaving(false)
    }
  }

  const handleSkip = () => {
    onNext()
  }

  const handleSkipPantryNudge = () => {
    // Skip the pantry marking, just save likes
    setSaving(true)
    setError('')
    
    apiRequest('/api/onboarding/pantry', {
      method: 'POST',
      body: JSON.stringify({
        items: selected.map(s => ({ 
          name: s.name, 
          category: s.category,
          in_pantry: false,
        })),
      }),
    }).then(() => onNext())
      .catch(err => {
        setError(err instanceof Error ? err.message : 'Failed to save')
        setSaving(false)
      })
  }

  // Group selected by category
  const groupedSelected = selected.reduce((acc, item) => {
    const cat = item.category || 'other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(item)
    return acc
  }, {} as Record<string, Ingredient[]>)

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          {showPantryNudge ? "Which do you have right now?" : "What ingredients do you love?"}
        </h2>
        <p className="text-[var(--color-text-muted)]">
          {showPantryNudge 
            ? "Tap ingredients you have in your kitchen, or search to add more. This helps Alfred suggest recipes you can make today."
            : "Add ingredients you enjoy cooking with. We'll use these to personalize your experience."
          }
        </p>
      </div>

      {error && (
        <div className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
          {error}
        </div>
      )}

      {/* Search Input */}
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          placeholder={showPantryNudge ? "Add more ingredients you have..." : "Search ingredients..."}
          className="w-full px-4 py-3 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-lg)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
        />
        {searching && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">
            ...
          </div>
        )}

        {/* Search Results Dropdown */}
        <AnimatePresence>
          {results.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="absolute top-full left-0 right-0 mt-2 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-lg overflow-hidden z-10"
            >
              {results.slice(0, 8).map(item => (
                <button
                  key={item.id}
                  onClick={() => addItem(item)}
                  className="w-full px-4 py-3 text-left hover:bg-[var(--color-bg-tertiary)] transition-colors flex items-center justify-between"
                >
                  <span className="text-[var(--color-text-primary)]">{item.name}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">{item.category}</span>
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Selected Items */}
      {selected.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
            {showPantryNudge ? `Tap what you have (${selected.filter(i => i.inPantry).length}/${selected.length})` : `Your Favorites (${selected.length})`}
          </h3>
          <div className="space-y-4">
            {Object.entries(groupedSelected).map(([category, items]) => (
              <div key={category}>
                <div className="text-xs text-[var(--color-text-muted)] mb-2 capitalize">
                  {category.replace(/_/g, ' ')}
                </div>
                <div className="flex flex-wrap gap-2">
                  <AnimatePresence>
                    {items.map(item => (
                      <motion.div
                        key={item.id}
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8 }}
                        onClick={showPantryNudge ? () => togglePantry(item.id) : undefined}
                        className={`
                          flex items-center gap-2 px-3 py-1.5 rounded-full transition-all
                          ${showPantryNudge 
                            ? item.inPantry 
                              ? 'bg-[var(--color-success)] text-white cursor-pointer' 
                              : 'bg-[var(--color-bg-tertiary)] cursor-pointer hover:bg-[var(--color-bg-elevated)]'
                            : 'bg-[var(--color-bg-tertiary)]'
                          }
                        `}
                      >
                        {showPantryNudge && item.inPantry && <span>✓</span>}
                        <span className="text-sm">{item.name}</span>
                        {!showPantryNudge && (
                          <button
                            onClick={() => removeItem(item.id)}
                            className="text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors"
                          >
                            ×
                          </button>
                        )}
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Empty State */}
      {selected.length === 0 && !showPantryNudge && (
        <div className="py-12 text-center">
          <div className="text-4xl mb-4">🥘</div>
          <p className="text-[var(--color-text-muted)]">
            Search for ingredients you love cooking with
          </p>
        </div>
      )}

      {/* Buttons */}
      <div className="pt-4 flex justify-between">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={showPantryNudge ? () => setShowPantryNudge(false) : onBack}
          className="px-6 py-3 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
        >
          ← Back
        </motion.button>
        <div className="flex gap-3">
          {showPantryNudge ? (
            <>
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleSkipPantryNudge}
                className="px-6 py-3 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
              >
                Skip this
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
            </>
          ) : (
            <>
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
                disabled={saving || selected.length === 0}
                className="px-8 py-3 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-semibold rounded-[var(--radius-lg)] transition-colors disabled:opacity-50"
              >
                {saving ? 'Saving...' : selected.length >= 3 ? 'Continue' : `Add ${3 - selected.length} more`}
              </motion.button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
