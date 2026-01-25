/**
 * IngredientsEditor - Sub-form for editing recipe ingredients.
 *
 * Each row: name (with autocomplete) | qty | unit dropdown | notes | optional checkbox | [x]
 * Used within RecipeEditor for creating/editing recipes.
 */

import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../../lib/api'
import type { FieldRendererProps } from '../FieldRenderer'

// =============================================================================
// Types
// =============================================================================

export interface RecipeIngredient {
  name: string
  ingredient_id: string | null  // Links to master ingredients table
  quantity: number | null
  unit: string | null
  notes: string | null
  is_optional: boolean
}

interface IngredientSuggestion {
  id: string
  name: string
  category: string | null
  default_unit: string | null
}

// Unit options (from FIELD_ENUMS inventory.unit)
const UNIT_OPTIONS = [
  'piece', 'lb', 'lbs', 'oz', 'kg', 'g',
  'gallon', 'gallons', 'cup', 'cups',
  'tbsp', 'tsp', 'ml', 'l',
  'can', 'carton', 'bottle', 'box', 'bag', 'bunch', 'head',
]

// =============================================================================
// IngredientsEditor Component
// =============================================================================

interface IngredientsEditorProps extends Omit<FieldRendererProps, 'schema'> {
  value: RecipeIngredient[]
  onChange: (value: RecipeIngredient[]) => void
}

export function IngredientsEditor({
  name,
  label,
  value = [],
  onChange,
  disabled,
  error,
}: IngredientsEditorProps) {
  const ingredients = value || []

  const handleAdd = () => {
    onChange([
      ...ingredients,
      { name: '', ingredient_id: null, quantity: null, unit: null, notes: null, is_optional: false },
    ])
  }

  const handleRemove = (index: number) => {
    onChange(ingredients.filter((_, i) => i !== index))
  }

  const handleUpdate = (index: number, updates: Partial<RecipeIngredient>) => {
    onChange(
      ingredients.map((ing, i) => (i === index ? { ...ing, ...updates } : ing))
    )
  }

  const formatLabel = (str: string) =>
    str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div className="space-y-3">
      {label !== undefined && (
        <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
          {label || formatLabel(name)}
        </label>
      )}

      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {ingredients.map((ingredient, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              layout
            >
              <IngredientRow
                ingredient={ingredient}
                index={index}
                onUpdate={(updates) => handleUpdate(index, updates)}
                onRemove={() => handleRemove(index)}
                disabled={disabled}
              />
            </motion.div>
          ))}
        </AnimatePresence>

        {ingredients.length === 0 && (
          <div className="p-4 rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)] border border-dashed border-[var(--color-border)] text-center text-[var(--color-text-muted)] text-sm">
            No ingredients yet. Click "Add Ingredient" to start.
          </div>
        )}
      </div>

      <motion.button
        type="button"
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        onClick={handleAdd}
        disabled={disabled}
        className="w-full px-4 py-2 rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        + Add Ingredient
      </motion.button>

      {error && <p className="text-xs text-[var(--color-error)]">{error}</p>}
    </div>
  )
}

// =============================================================================
// IngredientRow Component
// =============================================================================

interface IngredientRowProps {
  ingredient: RecipeIngredient
  index: number
  onUpdate: (updates: Partial<RecipeIngredient>) => void
  onRemove: () => void
  disabled?: boolean
}

function IngredientRow({
  ingredient,
  index,
  onUpdate,
  onRemove,
  disabled,
}: IngredientRowProps) {
  const [suggestions, setSuggestions] = useState<IngredientSuggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [searchQuery, setSearchQuery] = useState(ingredient.name)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Debounced search
  useEffect(() => {
    if (!searchQuery || searchQuery.length < 2) {
      setSuggestions([])
      return
    }

    const timer = setTimeout(async () => {
      try {
        const result = await apiRequest(`/api/ingredients/search?q=${encodeURIComponent(searchQuery)}`)
        setSuggestions(result.data || [])
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

  const handleSelectSuggestion = (suggestion: IngredientSuggestion) => {
    setSearchQuery(suggestion.name)
    onUpdate({
      name: suggestion.name,
      ingredient_id: suggestion.id,  // Link to master ingredients table
      unit: suggestion.default_unit || ingredient.unit,
    })
    setShowSuggestions(false)
  }

  const handleNameBlur = () => {
    // Sync the search query to ingredient name on blur
    if (searchQuery !== ingredient.name) {
      onUpdate({ name: searchQuery })
    }
    // Delay hiding to allow click on suggestion
    setTimeout(() => setShowSuggestions(false), 150)
  }

  const inputClasses = `
    px-2 py-1.5 rounded-[var(--radius-sm)]
    bg-[var(--color-bg-secondary)] border border-[var(--color-border)]
    text-[var(--color-text-primary)] text-sm
    focus:outline-none focus:border-[var(--color-accent)]
    disabled:opacity-50 disabled:cursor-not-allowed
  `

  return (
    <div className="flex items-center gap-2 p-3 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)]">
      {/* Index badge */}
      <span className="w-6 h-6 flex items-center justify-center rounded-full bg-[var(--color-bg-tertiary)] text-xs text-[var(--color-text-muted)]">
        {index + 1}
      </span>

      {/* Name with autocomplete */}
      <div className="relative flex-1 min-w-[140px]">
        <input
          ref={inputRef}
          type="text"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value)
            setShowSuggestions(true)
          }}
          onFocus={() => searchQuery.length >= 2 && setShowSuggestions(true)}
          onBlur={handleNameBlur}
          placeholder="Ingredient name"
          disabled={disabled}
          className={inputClasses + ' w-full'}
        />

        {/* Suggestions dropdown */}
        {showSuggestions && suggestions.length > 0 && (
          <div
            ref={dropdownRef}
            className="absolute z-50 w-full mt-1 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-lg max-h-48 overflow-y-auto"
          >
            {suggestions.map((sug) => (
              <button
                key={sug.id}
                type="button"
                onClick={() => handleSelectSuggestion(sug)}
                className="w-full px-3 py-2 text-left text-sm hover:bg-[var(--color-bg-tertiary)] transition-colors flex items-center justify-between"
              >
                <span className="text-[var(--color-text-primary)]">{sug.name}</span>
                {sug.category && (
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {sug.category}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Quantity */}
      <input
        type="number"
        value={ingredient.quantity ?? ''}
        onChange={(e) =>
          onUpdate({
            quantity: e.target.value === '' ? null : parseFloat(e.target.value),
          })
        }
        placeholder="Qty"
        disabled={disabled}
        min={0}
        step="any"
        className={inputClasses + ' w-16 text-center'}
      />

      {/* Unit dropdown */}
      <select
        value={ingredient.unit || ''}
        onChange={(e) => onUpdate({ unit: e.target.value || null })}
        disabled={disabled}
        className={inputClasses + ' w-20'}
      >
        <option value="">unit</option>
        {UNIT_OPTIONS.map((unit) => (
          <option key={unit} value={unit}>
            {unit}
          </option>
        ))}
      </select>

      {/* Notes */}
      <input
        type="text"
        value={ingredient.notes || ''}
        onChange={(e) => onUpdate({ notes: e.target.value || null })}
        placeholder="Notes (e.g. diced)"
        disabled={disabled}
        className={inputClasses + ' flex-1 min-w-[100px]'}
      />

      {/* Optional checkbox */}
      <label className="flex items-center gap-1 text-xs text-[var(--color-text-muted)] cursor-pointer">
        <input
          type="checkbox"
          checked={ingredient.is_optional}
          onChange={(e) => onUpdate({ is_optional: e.target.checked })}
          disabled={disabled}
          className="w-3.5 h-3.5 rounded border-[var(--color-border)]"
        />
        Opt
      </label>

      {/* Remove button */}
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors disabled:opacity-50"
        title="Remove ingredient"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  )
}

export default IngredientsEditor
