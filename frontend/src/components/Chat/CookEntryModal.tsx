/**
 * CookEntryModal - Recipe selection + notes modal for entering Cook mode.
 *
 * Follows RecipeImportModal pattern (framer-motion AnimatePresence).
 * Standalone recipe search — does not reuse form RecipePicker.
 */

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../lib/api'

interface Recipe {
  id: string
  name: string
  cuisine: string | null
}

interface CookEntryModalProps {
  isOpen: boolean
  onClose: () => void
  onStart: (recipeId: string, recipeName: string, notes: string) => void
}

export function CookEntryModal({ isOpen, onClose, onStart }: CookEntryModalProps) {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [notes, setNotes] = useState('')

  // Fetch recipes when modal opens
  useEffect(() => {
    if (!isOpen) return
    const fetchRecipes = async () => {
      setLoading(true)
      try {
        const data = await apiRequest('/api/entities/recipes')
        setRecipes(data.data || [])
      } catch (err) {
        console.error('Failed to fetch recipes:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchRecipes()
  }, [isOpen])

  const resetState = () => {
    setSearch('')
    setSelectedId(null)
    setNotes('')
  }

  const handleClose = () => {
    resetState()
    onClose()
  }

  const handleStart = () => {
    if (!selectedId) return
    const recipe = recipes.find(r => r.id === selectedId)
    if (!recipe) return
    const recipeName = recipe.name
    resetState()
    onStart(selectedId, recipeName, notes)
  }

  const filteredRecipes = recipes.filter(r =>
    r.name.toLowerCase().includes(search.toLowerCase()) ||
    (r.cuisine && r.cuisine.toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={handleClose}
        >
          <motion.div
            className="w-full max-w-md mx-4 bg-[var(--color-bg-elevated)] rounded-[var(--radius-lg)] shadow-xl overflow-hidden"
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
              <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Start Cooking</h2>
              <button
                type="button"
                onClick={handleClose}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              >
                &times;
              </button>
            </div>

            {/* Content */}
            <div className="px-5 py-4 space-y-4">
              {/* Recipe search */}
              <div>
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                  Recipe
                </label>
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search recipes..."
                  className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
                />
              </div>

              {/* Recipe list */}
              <div className="max-h-48 overflow-y-auto border border-[var(--color-border)] rounded-[var(--radius-md)]">
                {loading ? (
                  <div className="px-4 py-6 text-center text-sm text-[var(--color-text-muted)]">
                    Loading recipes...
                  </div>
                ) : filteredRecipes.length === 0 ? (
                  <div className="px-4 py-6 text-center text-sm text-[var(--color-text-muted)]">
                    {search ? 'No recipes match your search' : 'No recipes available'}
                  </div>
                ) : (
                  filteredRecipes.map((recipe) => (
                    <button
                      key={recipe.id}
                      type="button"
                      onClick={() => setSelectedId(recipe.id)}
                      className={`w-full px-4 py-2.5 text-left flex items-center gap-2 transition-colors border-b border-[var(--color-border)] last:border-b-0 ${
                        recipe.id === selectedId
                          ? 'bg-[var(--color-accent)] text-[var(--color-text-inverse)]'
                          : 'hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)]'
                      }`}
                    >
                      <span className="flex-1">{recipe.name}</span>
                      {recipe.cuisine && (
                        <span className={`px-2 py-0.5 text-xs rounded-full ${
                          recipe.id === selectedId
                            ? 'bg-white/20 text-[var(--color-text-inverse)]'
                            : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]'
                        }`}>
                          {recipe.cuisine}
                        </span>
                      )}
                    </button>
                  ))
                )}
              </div>

              {/* Notes */}
              <div>
                <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                  Notes <span className="font-normal text-[var(--color-text-muted)]">(optional)</span>
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Halving the recipe, substitutions..."
                  rows={2}
                  className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] resize-none focus:outline-none focus:border-[var(--color-accent)]"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-[var(--color-border)]">
              <button
                type="button"
                onClick={handleClose}
                className="px-4 py-2 text-sm rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleStart}
                disabled={!selectedId}
                className="px-4 py-2 text-sm font-semibold rounded-[var(--radius-md)] bg-[var(--color-accent)] text-[var(--color-text-inverse)] hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Start Cooking
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
