/**
 * RecipePicker - Searchable dropdown for selecting a recipe.
 *
 * Used for FK fields like recipe_id in MealPlan and Task forms.
 * Fetches recipes from /api/entities/recipes and displays them
 * with name + cuisine badge.
 */

import { useState, useEffect, useRef } from 'react'
import { apiRequest } from '../../../lib/api'
import type { FieldRendererProps } from '../FieldRenderer'

interface Recipe {
  id: string
  name: string
  cuisine: string | null
  difficulty: string | null
}

export function RecipePicker({
  name,
  label,
  value,
  onChange,
  required,
  error,
  disabled,
}: FieldRendererProps) {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(true)
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch recipes on mount
  useEffect(() => {
    const fetchRecipes = async () => {
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
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Filter recipes by search
  const filteredRecipes = recipes.filter((r) =>
    r.name.toLowerCase().includes(search.toLowerCase()) ||
    (r.cuisine && r.cuisine.toLowerCase().includes(search.toLowerCase()))
  )

  // Get selected recipe
  const selectedRecipe = recipes.find((r) => r.id === value)

  const handleSelect = (recipeId: string | null) => {
    onChange(recipeId)
    setIsOpen(false)
    setSearch('')
  }

  const formatLabel = (str: string) =>
    str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div className="space-y-1.5">
      {label !== undefined && (
        <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
          {label || formatLabel(name)}
          {required && <span className="text-[var(--color-error)] ml-1">*</span>}
        </label>
      )}

      <div ref={dropdownRef} className="relative">
        {/* Selected value / trigger */}
        <button
          type="button"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled}
          className={`
            w-full px-3 py-2 rounded-[var(--radius-md)] text-left
            bg-[var(--color-bg-secondary)] border border-[var(--color-border)]
            text-[var(--color-text-primary)]
            focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]
            disabled:opacity-50 disabled:cursor-not-allowed
            flex items-center justify-between
            ${error ? 'border-[var(--color-error)]' : ''}
          `}
        >
          {loading ? (
            <span className="text-[var(--color-text-muted)]">Loading...</span>
          ) : selectedRecipe ? (
            <span className="flex items-center gap-2">
              <span>{selectedRecipe.name}</span>
              {selectedRecipe.cuisine && (
                <span className="px-2 py-0.5 text-xs rounded-full bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]">
                  {selectedRecipe.cuisine}
                </span>
              )}
            </span>
          ) : (
            <span className="text-[var(--color-text-muted)]">Select a recipe...</span>
          )}
          <span className="text-[var(--color-text-muted)]">
            {isOpen ? '▲' : '▼'}
          </span>
        </button>

        {/* Dropdown */}
        {isOpen && (
          <div className="absolute z-50 w-full mt-1 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-lg max-h-64 overflow-hidden">
            {/* Search input */}
            <div className="p-2 border-b border-[var(--color-border)]">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search recipes..."
                className="w-full px-3 py-2 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
                autoFocus
              />
            </div>

            {/* Options */}
            <div className="overflow-y-auto max-h-48">
              {/* Clear option */}
              {value && (
                <button
                  type="button"
                  onClick={() => handleSelect(null)}
                  className="w-full px-3 py-2 text-left text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-bg-tertiary)] border-b border-[var(--color-border)]"
                >
                  Clear selection
                </button>
              )}

              {filteredRecipes.length === 0 ? (
                <div className="px-3 py-4 text-center text-[var(--color-text-muted)] text-sm">
                  {search ? 'No recipes match your search' : 'No recipes available'}
                </div>
              ) : (
                filteredRecipes.map((recipe) => (
                  <button
                    key={recipe.id}
                    type="button"
                    onClick={() => handleSelect(recipe.id)}
                    className={`
                      w-full px-3 py-2 text-left flex items-center gap-2
                      hover:bg-[var(--color-bg-tertiary)] transition-colors
                      ${recipe.id === value ? 'bg-[var(--color-accent-muted)]' : ''}
                    `}
                  >
                    <span className="flex-1 text-[var(--color-text-primary)]">
                      {recipe.name}
                    </span>
                    {recipe.cuisine && (
                      <span className="px-2 py-0.5 text-xs rounded-full bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]">
                        {recipe.cuisine}
                      </span>
                    )}
                    {recipe.difficulty && (
                      <span className={`
                        px-2 py-0.5 text-xs rounded-full
                        ${recipe.difficulty === 'easy' ? 'bg-green-500/10 text-green-500' : ''}
                        ${recipe.difficulty === 'medium' ? 'bg-yellow-500/10 text-yellow-500' : ''}
                        ${recipe.difficulty === 'hard' ? 'bg-red-500/10 text-red-500' : ''}
                      `}>
                        {recipe.difficulty}
                      </span>
                    )}
                  </button>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {error && (
        <p className="text-xs text-[var(--color-error)]">{error}</p>
      )}
    </div>
  )
}
