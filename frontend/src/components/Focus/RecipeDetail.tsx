import { useEffect, useState } from 'react'
import { apiRequest } from '../../lib/api'

interface Recipe {
  id: string
  name: string
  cuisine: string | null
  difficulty: string | null
  prep_time_minutes: number | null
  cook_time_minutes: number | null
  servings: number | null
  instructions: string[] | null
  tags: string[] | null
}

interface Ingredient {
  id: string
  name: string
  quantity: number | null
  unit: string | null
  is_optional: boolean
}

interface RecipeDetailProps {
  id: string
  onClose?: () => void
}

export function RecipeDetail({ id, onClose }: RecipeDetailProps) {
  const [recipe, setRecipe] = useState<Recipe | null>(null)
  const [ingredients, setIngredients] = useState<Ingredient[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    fetchRecipe()
  }, [id])

  const fetchRecipe = async () => {
    try {
      // Fetch recipe
      const recipeData = await apiRequest('/api/tables/recipes')
      const foundRecipe = recipeData.data?.find((r: Recipe) => r.id === id)
      setRecipe(foundRecipe || null)

      // Fetch ingredients
      if (foundRecipe) {
        const ingredientsData = await apiRequest(`/api/tables/recipes/${id}/ingredients`)
        setIngredients(ingredientsData.data || [])
      }
    } catch (err) {
      console.error('Failed to fetch recipe:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!recipe) return
    if (!confirm(`Delete "${recipe.name}"? This cannot be undone.`)) return
    
    setDeleting(true)
    try {
      await apiRequest(`/api/tables/recipes/${recipe.id}`, {
        method: 'DELETE',
      })
      // Close the focus overlay after delete
      onClose?.()
    } catch (err) {
      console.error('Failed to delete recipe:', err)
      alert('Failed to delete recipe')
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-[var(--color-text-muted)]">Loading recipe...</div>
      </div>
    )
  }

  if (!recipe) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-[var(--color-text-muted)]">Recipe not found</div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
          {recipe.name}
        </h1>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="px-3 py-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10 rounded-[var(--radius-sm)] transition-colors disabled:opacity-50"
          title="Delete recipe"
        >
          {deleting ? 'Deleting...' : '🗑️ Delete'}
        </button>
      </div>

      {/* Meta */}
      <div className="flex flex-wrap gap-4 text-sm text-[var(--color-text-muted)] mb-6 pb-6 border-b border-[var(--color-border)]">
        {recipe.prep_time_minutes && (
          <span>Prep: {recipe.prep_time_minutes} min</span>
        )}
        {recipe.cook_time_minutes && (
          <span>Cook: {recipe.cook_time_minutes} min</span>
        )}
        {recipe.servings && <span>Serves: {recipe.servings}</span>}
        {recipe.difficulty && (
          <span className="px-2 py-0.5 bg-[var(--color-accent-muted)] text-[var(--color-accent)] rounded-[var(--radius-sm)]">
            {recipe.difficulty}
          </span>
        )}
      </div>

      {/* Ingredients */}
      {ingredients.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-medium text-[var(--color-text-primary)] mb-4">
            Ingredients
          </h2>
          <ul className="space-y-2">
            {ingredients.map((ing) => (
              <li
                key={ing.id}
                className="flex items-center gap-3 text-[var(--color-text-secondary)]"
              >
                <span className="w-5 h-5 rounded border border-[var(--color-border)] flex items-center justify-center text-xs">
                  □
                </span>
                <span>
                  {ing.quantity} {ing.unit} {ing.name}
                  {ing.is_optional && (
                    <span className="text-[var(--color-text-muted)]"> (optional)</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Instructions */}
      {recipe.instructions && recipe.instructions.length > 0 && (
        <section>
          <h2 className="text-lg font-medium text-[var(--color-text-primary)] mb-4">
            Instructions
          </h2>
          <ol className="space-y-4">
            {recipe.instructions.map((step, i) => (
              <li key={i} className="flex gap-4">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[var(--color-accent-muted)] text-[var(--color-accent)] flex items-center justify-center text-sm font-medium">
                  {i + 1}
                </span>
                <p className="text-[var(--color-text-secondary)] leading-relaxed">
                  {step}
                </p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Tags */}
      {recipe.tags && recipe.tags.length > 0 && (
        <div className="mt-8 pt-6 border-t border-[var(--color-border)]">
          <div className="flex flex-wrap gap-2">
            {recipe.tags.map((tag) => (
              <span
                key={tag}
                className="px-3 py-1 bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)] rounded-full text-sm"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

