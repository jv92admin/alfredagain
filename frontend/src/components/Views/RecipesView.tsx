import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { useUIChanges } from '../../context/ChatContext'
import { IngredientsEditor, type RecipeIngredient } from '../Form/editors'
import { StepsEditor } from '../Form/editors'

interface Recipe {
  id: string
  name: string
  description: string | null
  cuisine: string | null
  difficulty: string | null
  prep_time_minutes: number | null
  cook_time_minutes: number | null
  servings: number | null
  tags: string[] | null
  instructions: string[] | null
  source_url: string | null
  created_at: string
}

interface RecipeFormData {
  name: string
  description: string
  cuisine: string
  difficulty: string
  prep_time_minutes: number | null
  cook_time_minutes: number | null
  servings: number | null
  source_url: string
  tags: string[]
  instructions: string[]
  ingredients: RecipeIngredient[]
}

const CUISINE_OPTIONS = ['italian', 'mexican', 'chinese', 'indian', 'american', 'french', 'japanese', 'thai', 'mediterranean', 'korean']
const DIFFICULTY_OPTIONS = ['easy', 'medium', 'hard']

const initialFormData: RecipeFormData = {
  name: '',
  description: '',
  cuisine: '',
  difficulty: '',
  prep_time_minutes: null,
  cook_time_minutes: null,
  servings: null,
  source_url: '',
  tags: [],
  instructions: [],
  ingredients: [],
}

interface RecipesViewProps {
  onOpenFocus: (item: { type: string; id: string }) => void
}

export function RecipesView({ onOpenFocus }: RecipesViewProps) {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingRecipe, setEditingRecipe] = useState<Recipe | null>(null)
  const [formData, setFormData] = useState<RecipeFormData>(initialFormData)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [loadingIngredients, setLoadingIngredients] = useState(false)
  const { pushUIChange } = useUIChanges()

  useEffect(() => {
    fetchRecipes()
  }, [])

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

  const openCreateModal = () => {
    setEditingRecipe(null)
    setFormData(initialFormData)
    setFormError(null)
    setShowModal(true)
  }

  const openEditModal = async (recipe: Recipe) => {
    setEditingRecipe(recipe)
    setFormError(null)
    setLoadingIngredients(true)
    setShowModal(true)

    // Pre-fill form with recipe data
    setFormData({
      name: recipe.name,
      description: recipe.description || '',
      cuisine: recipe.cuisine || '',
      difficulty: recipe.difficulty || '',
      prep_time_minutes: recipe.prep_time_minutes,
      cook_time_minutes: recipe.cook_time_minutes,
      servings: recipe.servings,
      source_url: recipe.source_url || '',
      tags: recipe.tags || [],
      instructions: recipe.instructions || [],
      ingredients: [], // Will be loaded
    })

    // Fetch ingredients
    try {
      const ingredientsData = await apiRequest(`/api/tables/recipes/${recipe.id}/ingredients`)
      const ingredients: RecipeIngredient[] = (ingredientsData.data || []).map((ing: any) => ({
        name: ing.name || '',
        ingredient_id: ing.ingredient_id || null,  // May be linked to master ingredients
        quantity: ing.quantity,
        unit: ing.unit,
        notes: ing.notes,
        is_optional: ing.is_optional || false,
      }))
      setFormData(prev => ({ ...prev, ingredients }))
    } catch (err) {
      console.error('Failed to fetch ingredients:', err)
    } finally {
      setLoadingIngredients(false)
    }
  }

  const closeModal = () => {
    setShowModal(false)
    setEditingRecipe(null)
    setFormData(initialFormData)
    setFormError(null)
  }

  const handleSubmit = async () => {
    if (!formData.name.trim()) {
      setFormError('Recipe name is required')
      return
    }
    if (formData.instructions.length === 0 || formData.instructions.every(s => !s.trim())) {
      setFormError('At least one instruction step is required')
      return
    }

    setSubmitting(true)
    setFormError(null)

    try {
      // Filter out empty instructions
      const cleanInstructions = formData.instructions.filter(s => s.trim())
      // Filter out empty ingredients
      const cleanIngredients = formData.ingredients
        .filter(ing => ing.name.trim())
        .map(ing => ({
          name: ing.name,
          ingredient_id: ing.ingredient_id,  // Link to master ingredients table
          quantity: ing.quantity,
          unit: ing.unit,
          notes: ing.notes,
          is_optional: ing.is_optional,
        }))

      const payload = {
        name: formData.name,
        description: formData.description || null,
        cuisine: formData.cuisine || null,
        difficulty: formData.difficulty || null,
        prep_time_minutes: formData.prep_time_minutes,
        cook_time_minutes: formData.cook_time_minutes,
        servings: formData.servings,
        source_url: formData.source_url || null,
        tags: formData.tags,
        instructions: cleanInstructions,
        ingredients: cleanIngredients,
      }

      if (editingRecipe) {
        // Update existing recipe
        const result = await apiRequest(`/api/entities/recipes/${editingRecipe.id}/with-ingredients`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
        setRecipes(prev => prev.map(r => r.id === editingRecipe.id ? { ...r, ...result.data } : r))
        // Track UI change for AI context
        pushUIChange({
          action: 'updated:user',
          entity_type: 'recipe',
          id: editingRecipe.id,
          label: formData.name,
          data: result.data,
        })
      } else {
        // Create new recipe
        const result = await apiRequest('/api/entities/recipes/with-ingredients', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        setRecipes(prev => [...prev, result.data])
        // Track UI change for AI context
        pushUIChange({
          action: 'created:user',
          entity_type: 'recipe',
          id: result.data.id,
          label: result.data.name,
          data: result.data,
        })
      }

      closeModal()
    } catch (err) {
      console.error('Failed to save recipe:', err)
      setFormError(`Failed to ${editingRecipe ? 'update' : 'create'} recipe. Please try again.`)
    } finally {
      setSubmitting(false)
    }
  }

  const deleteRecipe = async (e: React.MouseEvent, recipe: Recipe) => {
    e.stopPropagation()
    if (!confirm(`Delete "${recipe.name}"?`)) return

    // Optimistic update
    setRecipes(prev => prev.filter(r => r.id !== recipe.id))

    try {
      await apiRequest(`/api/entities/recipes/${recipe.id}`, {
        method: 'DELETE',
      })
      // Track UI change for AI context
      pushUIChange({
        action: 'deleted:user',
        entity_type: 'recipe',
        id: recipe.id,
        label: recipe.name,
      })
    } catch (err) {
      // Revert on error
      setRecipes(prev => [...prev, recipe])
      console.error('Failed to delete recipe:', err)
    }
  }

  const updateFormField = <K extends keyof RecipeFormData>(field: K, value: RecipeFormData[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  // Recipe Modal - defined early so it can be used in all return branches
  const recipeModal = (
    <AnimatePresence>
      {showModal && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          onClick={closeModal}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-[var(--color-bg-primary)] rounded-[var(--radius-lg)] shadow-xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
              <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">
                {editingRecipe ? 'Edit Recipe' : 'Create Recipe'}
              </h2>
              <button
                onClick={closeModal}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Form content - scrollable */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Basic Info */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                    Name <span className="text-[var(--color-error)]">*</span>
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => updateFormField('name', e.target.value)}
                    placeholder="Recipe name"
                    className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                    Description
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => updateFormField('description', e.target.value)}
                    placeholder="Brief description of the recipe"
                    rows={2}
                    className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)] resize-y"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                    Cuisine
                  </label>
                  <select
                    value={formData.cuisine}
                    onChange={(e) => updateFormField('cuisine', e.target.value)}
                    className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
                  >
                    <option value="">Select cuisine...</option>
                    {CUISINE_OPTIONS.map((opt) => (
                      <option key={opt} value={opt}>{opt.charAt(0).toUpperCase() + opt.slice(1)}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                    Difficulty
                  </label>
                  <select
                    value={formData.difficulty}
                    onChange={(e) => updateFormField('difficulty', e.target.value)}
                    className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
                  >
                    <option value="">Select difficulty...</option>
                    {DIFFICULTY_OPTIONS.map((opt) => (
                      <option key={opt} value={opt}>{opt.charAt(0).toUpperCase() + opt.slice(1)}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                    Prep Time (min)
                  </label>
                  <input
                    type="number"
                    value={formData.prep_time_minutes ?? ''}
                    onChange={(e) => updateFormField('prep_time_minutes', e.target.value ? parseInt(e.target.value) : null)}
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
                    value={formData.cook_time_minutes ?? ''}
                    onChange={(e) => updateFormField('cook_time_minutes', e.target.value ? parseInt(e.target.value) : null)}
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
                    value={formData.servings ?? ''}
                    onChange={(e) => updateFormField('servings', e.target.value ? parseInt(e.target.value) : null)}
                    min={1}
                    className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                    Source URL
                  </label>
                  <input
                    type="url"
                    value={formData.source_url}
                    onChange={(e) => updateFormField('source_url', e.target.value)}
                    placeholder="https://..."
                    className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
                  />
                </div>
              </div>

              {/* Ingredients */}
              <div>
                {loadingIngredients ? (
                  <div className="p-4 rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-center text-[var(--color-text-muted)] text-sm">
                    Loading ingredients...
                  </div>
                ) : (
                  <IngredientsEditor
                    name="ingredients"
                    label="Ingredients"
                    value={formData.ingredients}
                    onChange={(val) => updateFormField('ingredients', val)}
                  />
                )}
              </div>

              {/* Instructions */}
              <div>
                <StepsEditor
                  name="instructions"
                  label="Instructions *"
                  value={formData.instructions}
                  onChange={(val) => updateFormField('instructions', val)}
                />
              </div>

              {/* Error message */}
              {formError && (
                <div className="p-3 rounded-[var(--radius-md)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 text-[var(--color-error)] text-sm">
                  {formError}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-[var(--color-border)]">
              <button
                onClick={closeModal}
                className="px-4 py-2 rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
              >
                Cancel
              </button>
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleSubmit}
                disabled={submitting || loadingIngredients}
                className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)] disabled:opacity-50"
              >
                {submitting ? (editingRecipe ? 'Saving...' : 'Creating...') : (editingRecipe ? 'Save Changes' : 'Create Recipe')}
              </motion.button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading recipes...</div>
      </div>
    )
  }

  if (recipes.length === 0) {
    return (
      <>
        <div className="flex flex-col items-center justify-center h-full text-center p-8">
          <span className="text-4xl mb-4">🍳</span>
          <h2 className="text-xl text-[var(--color-text-primary)] mb-2">No recipes yet</h2>
          <p className="text-[var(--color-text-muted)] mb-4">
            Ask Alfred to create some recipes for you!
          </p>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={openCreateModal}
            className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)]"
          >
            + Add Recipe
          </motion.button>
        </div>
        {recipeModal}
      </>
    )
  }

  return (
    <>
      <div className="h-full overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
            Recipes
          </h1>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={openCreateModal}
            className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)] text-sm"
          >
            + Add Recipe
          </motion.button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {recipes.map((recipe) => (
            <div
              key={recipe.id}
              className="group relative bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 hover:border-[var(--color-accent)] transition-colors"
            >
              {/* Actions */}
              <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    openEditModal(recipe)
                  }}
                  className="p-1.5 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-colors"
                  title="Edit"
                >
                  ✏️
                </button>
                <button
                  onClick={(e) => deleteRecipe(e, recipe)}
                  className="p-1.5 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors"
                  title="Delete"
                >
                  🗑️
                </button>
              </div>

              <button
                onClick={() => onOpenFocus({ type: 'recipe', id: recipe.id })}
                className="w-full text-left"
              >
                <h3 className="font-medium text-[var(--color-text-primary)] mb-2 pr-16">
                  {recipe.name}
                </h3>
                <div className="flex flex-wrap gap-2 text-sm text-[var(--color-text-muted)]">
                  {recipe.cuisine && (
                    <span className="px-2 py-0.5 bg-[var(--color-bg-tertiary)] rounded-[var(--radius-sm)]">
                      {recipe.cuisine}
                    </span>
                  )}
                  {recipe.difficulty && (
                    <span className="px-2 py-0.5 bg-[var(--color-accent-muted)] text-[var(--color-accent)] rounded-[var(--radius-sm)]">
                      {recipe.difficulty}
                    </span>
                  )}
                </div>
                <div className="mt-3 text-xs text-[var(--color-text-muted)]">
                  {(recipe.prep_time_minutes || 0) + (recipe.cook_time_minutes || 0)} min
                  {recipe.servings && ` · ${recipe.servings} servings`}
                </div>
              </button>
            </div>
          ))}
        </div>
      </div>
      {recipeModal}
    </>
  )
}

