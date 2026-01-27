import { useState } from 'react'
import { motion } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { useUIChanges } from '../../context/ChatContext'

interface ParsedIngredient {
  name: string
  quantity: number | null
  unit: string | null
  notes: string | null
  is_optional: boolean
  raw_text: string | null
  ingredient_id: string | null
  match_confidence: number
}

interface RecipePreview {
  name: string
  source_url: string
  description: string | null
  prep_time_minutes: number | null
  cook_time_minutes: number | null
  servings: number | null
  cuisine: string | null
  ingredients_raw: string[]
  ingredients_parsed?: ParsedIngredient[]
  instructions: string[]
  image_url: string | null
}

interface IngredientFormData {
  name: string
  quantity: string  // Keep as string for input, convert on save
  unit: string
  notes: string
  is_optional: boolean
  ingredient_id: string | null  // Link to master ingredients DB
}

interface RecipePreviewFormProps {
  preview: RecipePreview
  onSave: () => void
  onCancel: () => void
  onSaving: () => void
  onSaveError: () => void
}

const CUISINE_OPTIONS = ['italian', 'mexican', 'chinese', 'indian', 'american', 'french', 'japanese', 'thai', 'mediterranean', 'korean']

// Initialize ingredients from parsed data or fall back to raw strings
function initializeIngredients(preview: RecipePreview): IngredientFormData[] {
  if (preview.ingredients_parsed && preview.ingredients_parsed.length > 0) {
    return preview.ingredients_parsed.map(p => ({
      name: p.name || '',
      quantity: p.quantity !== null ? String(p.quantity) : '',
      unit: p.unit || '',
      notes: p.notes || '',
      is_optional: p.is_optional || false,
      ingredient_id: p.ingredient_id || null,
    }))
  }

  // Fallback to raw strings
  if (preview.ingredients_raw && preview.ingredients_raw.length > 0) {
    return preview.ingredients_raw.map(raw => ({
      name: raw,
      quantity: '',
      unit: '',
      notes: '',
      is_optional: false,
      ingredient_id: null,
    }))
  }

  return [{ name: '', quantity: '', unit: '', notes: '', is_optional: false, ingredient_id: null }]
}

export function RecipePreviewForm({ preview, onSave, onCancel, onSaving, onSaveError }: RecipePreviewFormProps) {
  const { pushUIChange } = useUIChanges()

  // Form state initialized from preview
  const [name, setName] = useState(preview.name)
  const [description, setDescription] = useState(preview.description || '')
  const [prepTime, setPrepTime] = useState<number | null>(preview.prep_time_minutes)
  const [cookTime, setCookTime] = useState<number | null>(preview.cook_time_minutes)
  const [servings, setServings] = useState<number | null>(preview.servings)
  const [cuisine, setCuisine] = useState(preview.cuisine || '')
  const [instructions, setInstructions] = useState<string[]>(preview.instructions.length > 0 ? preview.instructions : [''])
  const [ingredients, setIngredients] = useState<IngredientFormData[]>(initializeIngredients(preview))
  const [error, setError] = useState<string | null>(null)

  const sourceHost = new URL(preview.source_url).hostname.replace('www.', '')

  const handleSave = async () => {
    // Validation
    if (!name.trim()) {
      setError('Recipe name is required')
      return
    }

    const cleanInstructions = instructions.filter(s => s.trim())
    if (cleanInstructions.length === 0) {
      setError('At least one instruction step is required')
      return
    }

    setError(null)
    onSaving()

    try {
      // Convert ingredients to API format
      const apiIngredients = ingredients
        .filter(ing => ing.name.trim())
        .map(ing => ({
          name: ing.name.trim(),
          quantity: ing.quantity ? parseFloat(ing.quantity) : null,
          unit: ing.unit.trim() || null,
          notes: ing.notes.trim() || null,
          is_optional: ing.is_optional,
          ingredient_id: ing.ingredient_id,
        }))

      const response = await apiRequest('/api/recipes/import/confirm', {
        method: 'POST',
        body: JSON.stringify({
          source_url: preview.source_url,
          name: name.trim(),
          description: description.trim() || null,
          prep_time_minutes: prepTime,
          cook_time_minutes: cookTime,
          servings: servings,
          cuisine: cuisine || null,
          instructions: cleanInstructions,
          tags: [],
          ingredients: apiIngredients,
        }),
      })

      if (response.success) {
        // Track UI change for AI context
        pushUIChange({
          action: 'created:user',
          entity_type: 'recipe',
          id: response.recipe_id,
          label: name,
          data: { source: 'import', source_url: preview.source_url },
        })
        onSave()
      } else {
        setError(response.error || 'Failed to save recipe')
        onSaveError()
      }
    } catch (err) {
      console.error('Save error:', err)
      setError('Failed to save recipe. Please try again.')
      onSaveError()
    }
  }

  const updateInstruction = (index: number, value: string) => {
    const newInstructions = [...instructions]
    newInstructions[index] = value
    setInstructions(newInstructions)
  }

  const addInstruction = () => {
    setInstructions([...instructions, ''])
  }

  const removeInstruction = (index: number) => {
    if (instructions.length > 1) {
      setInstructions(instructions.filter((_, i) => i !== index))
    }
  }

  const updateIngredient = (index: number, field: keyof IngredientFormData, value: string | boolean) => {
    const newIngredients = [...ingredients]
    newIngredients[index] = { ...newIngredients[index], [field]: value }
    setIngredients(newIngredients)
  }

  const addIngredient = () => {
    setIngredients([...ingredients, { name: '', quantity: '', unit: '', notes: '', is_optional: false, ingredient_id: null }])
  }

  const removeIngredient = (index: number) => {
    if (ingredients.length > 1) {
      setIngredients(ingredients.filter((_, i) => i !== index))
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Success banner */}
      <div className="px-6 py-3 bg-[var(--color-success)]/10 border-b border-[var(--color-success)]/30">
        <div className="flex items-center gap-2 text-[var(--color-success)]">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          <span className="text-sm font-medium">Recipe imported from {sourceHost}</span>
        </div>
      </div>

      {/* Form - scrollable */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Basic Info */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
              Name <span className="text-[var(--color-error)]">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)] resize-y"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
              Prep Time (min)
            </label>
            <input
              type="number"
              value={prepTime ?? ''}
              onChange={(e) => setPrepTime(e.target.value ? parseInt(e.target.value) : null)}
              min={0}
              className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
              Cook Time (min)
            </label>
            <input
              type="number"
              value={cookTime ?? ''}
              onChange={(e) => setCookTime(e.target.value ? parseInt(e.target.value) : null)}
              min={0}
              className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
              Servings
            </label>
            <input
              type="number"
              value={servings ?? ''}
              onChange={(e) => setServings(e.target.value ? parseInt(e.target.value) : null)}
              min={1}
              className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
              Cuisine
            </label>
            <select
              value={cuisine}
              onChange={(e) => setCuisine(e.target.value)}
              className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
            >
              <option value="">Select cuisine...</option>
              {CUISINE_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>{opt.charAt(0).toUpperCase() + opt.slice(1)}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Ingredients - Structured */}
        <div>
          <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
            Ingredients
          </label>
          <div className="space-y-3">
            {ingredients.map((ingredient, index) => (
              <div key={index} className="p-3 rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)] border border-[var(--color-border)]">
                {/* Mobile: stacked layout, Desktop: horizontal */}
                <div className="flex flex-col md:flex-row md:items-center gap-2">
                  {/* Qty + Unit row (always inline) */}
                  <div className="flex gap-2 md:w-auto">
                    <input
                      type="text"
                      value={ingredient.quantity}
                      onChange={(e) => updateIngredient(index, 'quantity', e.target.value)}
                      placeholder="Qty"
                      className="w-16 md:w-14 px-2 py-1.5 rounded-[var(--radius-sm)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                    />
                    <input
                      type="text"
                      value={ingredient.unit}
                      onChange={(e) => updateIngredient(index, 'unit', e.target.value)}
                      placeholder="Unit"
                      className="w-20 md:w-16 px-2 py-1.5 rounded-[var(--radius-sm)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                    />
                  </div>
                  {/* Name - grows to fill */}
                  <input
                    type="text"
                    value={ingredient.name}
                    onChange={(e) => updateIngredient(index, 'name', e.target.value)}
                    placeholder="Ingredient name"
                    className="flex-1 min-w-0 px-2 py-1.5 rounded-[var(--radius-sm)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                  />
                  {/* Notes */}
                  <input
                    type="text"
                    value={ingredient.notes}
                    onChange={(e) => updateIngredient(index, 'notes', e.target.value)}
                    placeholder="Notes (minced, fresh...)"
                    className="flex-1 min-w-0 md:max-w-[180px] px-2 py-1.5 rounded-[var(--radius-sm)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-muted)] text-sm focus:outline-none focus:border-[var(--color-accent)]"
                  />
                  {/* Optional + Remove */}
                  <div className="flex items-center gap-2 justify-between md:justify-end">
                    <label className="flex items-center gap-1 text-xs text-[var(--color-text-muted)] whitespace-nowrap">
                      <input
                        type="checkbox"
                        checked={ingredient.is_optional}
                        onChange={(e) => updateIngredient(index, 'is_optional', e.target.checked)}
                        className="rounded border-[var(--color-border)]"
                      />
                      Optional
                    </label>
                    <button
                      onClick={() => removeIngredient(index)}
                      disabled={ingredients.length <= 1}
                      className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-error)] disabled:opacity-30"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            ))}
            <button
              onClick={addIngredient}
              className="text-sm text-[var(--color-accent)] hover:text-[var(--color-accent-hover)]"
            >
              + Add ingredient
            </button>
          </div>
          {ingredients.filter(ing => ing.name.trim()).length === 0 && (
            <p className="mt-1 text-xs text-[var(--color-warning)]">No ingredients found - you may want to add them manually</p>
          )}
        </div>

        {/* Instructions */}
        <div>
          <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
            Instructions <span className="text-[var(--color-error)]">*</span>
          </label>
          <div className="space-y-2">
            {instructions.map((instruction, index) => (
              <div key={index} className="flex gap-2">
                <span className="flex-shrink-0 w-6 h-10 flex items-center justify-center text-sm text-[var(--color-text-muted)]">
                  {index + 1}.
                </span>
                <textarea
                  value={instruction}
                  onChange={(e) => updateInstruction(index, e.target.value)}
                  placeholder="Instruction step..."
                  rows={2}
                  className="flex-1 px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)] resize-y"
                />
                <button
                  onClick={() => removeInstruction(index)}
                  disabled={instructions.length <= 1}
                  className="p-2 text-[var(--color-text-muted)] hover:text-[var(--color-error)] disabled:opacity-30 self-start mt-1"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </button>
              </div>
            ))}
            <button
              onClick={addInstruction}
              className="text-sm text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] ml-8"
            >
              + Add step
            </button>
          </div>
        </div>

        {/* Source attribution */}
        <div className="text-sm text-[var(--color-text-muted)]">
          Source: <a href={preview.source_url} target="_blank" rel="noopener noreferrer" className="text-[var(--color-accent)] hover:underline">{sourceHost}</a>
        </div>

        {/* Error message */}
        {error && (
          <div className="p-3 rounded-[var(--radius-md)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 text-[var(--color-error)] text-sm">
            {error}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex justify-end gap-3 px-6 py-4 border-t border-[var(--color-border)]">
        <button
          onClick={onCancel}
          className="px-4 py-2 rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
        >
          Cancel
        </button>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleSave}
          className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)]"
        >
          Save Recipe
        </motion.button>
      </div>
    </div>
  )
}
