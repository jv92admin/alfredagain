import { useEffect, useState } from 'react'

interface MealPlan {
  id: string
  date: string
  meal_type: string
  recipe_id: string | null
  notes: string | null
  servings: number | null
}

interface Recipe {
  id: string
  name: string
  cuisine: string | null
  prep_time_minutes: number | null
  cook_time_minutes: number | null
}

interface MealPlanDetailProps {
  id: string
  onOpenFocus?: (item: { type: string; id: string }) => void
}

export function MealPlanDetail({ id, onOpenFocus }: MealPlanDetailProps) {
  const [mealPlan, setMealPlan] = useState<MealPlan | null>(null)
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null)
  const [loading, setLoading] = useState(true)
  const [showRecipeSelector, setShowRecipeSelector] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchData()
  }, [id])

  const fetchData = async () => {
    try {
      // Fetch meal plans and recipes in parallel
      const [mealRes, recipeRes] = await Promise.all([
        fetch('/api/tables/meal_plans', { credentials: 'include' }),
        fetch('/api/tables/recipes', { credentials: 'include' }),
      ])
      
      const mealData = await mealRes.json()
      const recipeData = await recipeRes.json()
      
      const found = mealData.data?.find((m: MealPlan) => m.id === id)
      setMealPlan(found || null)
      setRecipes(recipeData.data || [])
      
      // If meal plan has a recipe, find it
      if (found?.recipe_id) {
        const linkedRecipe = recipeData.data?.find((r: Recipe) => r.id === found.recipe_id)
        setSelectedRecipe(linkedRecipe || null)
      }
    } catch (err) {
      console.error('Failed to fetch data:', err)
    } finally {
      setLoading(false)
    }
  }

  const assignRecipe = async (recipe: Recipe | null) => {
    if (!mealPlan) return
    
    setSaving(true)
    setSelectedRecipe(recipe)
    setShowRecipeSelector(false)
    
    try {
      await fetch(`/api/tables/meal_plans/${mealPlan.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipe_id: recipe?.id || null }),
        credentials: 'include',
      })
      
      // Update local state
      setMealPlan(prev => prev ? { ...prev, recipe_id: recipe?.id || null } : null)
    } catch (err) {
      console.error('Failed to assign recipe:', err)
      // Revert on error
      setSelectedRecipe(mealPlan.recipe_id ? recipes.find(r => r.id === mealPlan.recipe_id) || null : null)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-[var(--color-text-muted)]">Loading meal plan...</div>
      </div>
    )
  }

  if (!mealPlan) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-[var(--color-text-muted)]">Meal plan not found</div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <span className="inline-block px-3 py-1 bg-[var(--color-accent-muted)] text-[var(--color-accent)] rounded-[var(--radius-sm)] text-sm capitalize mb-2">
          {mealPlan.meal_type}
        </span>
        <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
          {new Date(mealPlan.date).toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
          })}
        </h1>
      </div>

      {/* Recipe Section */}
      <div className="mb-6">
        <h2 className="text-sm font-medium text-[var(--color-text-muted)] mb-3">
          Recipe
        </h2>
        
        {showRecipeSelector ? (
          <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden">
            {/* No recipe option */}
            <button
              onClick={() => assignRecipe(null)}
              className="w-full text-left px-4 py-3 hover:bg-[var(--color-bg-tertiary)] transition-colors border-b border-[var(--color-border)]"
            >
              <span className="text-[var(--color-text-muted)] italic">No recipe (notes only)</span>
            </button>
            
            {/* Recipe list */}
            {recipes.length > 0 ? (
              recipes.map((recipe) => (
                <button
                  key={recipe.id}
                  onClick={() => assignRecipe(recipe)}
                  className={`w-full text-left px-4 py-3 hover:bg-[var(--color-bg-tertiary)] transition-colors border-b border-[var(--color-border)] last:border-b-0 ${
                    selectedRecipe?.id === recipe.id ? 'bg-[var(--color-accent-muted)]' : ''
                  }`}
                >
                  <div className="text-[var(--color-text-primary)]">{recipe.name}</div>
                  <div className="text-sm text-[var(--color-text-muted)]">
                    {recipe.cuisine && <span>{recipe.cuisine} • </span>}
                    {(recipe.prep_time_minutes || recipe.cook_time_minutes) && (
                      <span>{(recipe.prep_time_minutes || 0) + (recipe.cook_time_minutes || 0)} min</span>
                    )}
                  </div>
                </button>
              ))
            ) : (
              <div className="px-4 py-6 text-center">
                <p className="text-[var(--color-text-muted)] mb-2">No recipes yet</p>
                <p className="text-sm text-[var(--color-accent)]">
                  💡 Ask Alfred to create a recipe for this meal!
                </p>
              </div>
            )}
            
            {/* Cancel */}
            <button
              onClick={() => setShowRecipeSelector(false)}
              className="w-full px-4 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] bg-[var(--color-bg-tertiary)]"
            >
              Cancel
            </button>
          </div>
        ) : selectedRecipe ? (
          <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[var(--color-text-primary)] font-medium">{selectedRecipe.name}</div>
                <div className="text-sm text-[var(--color-text-muted)]">
                  {selectedRecipe.cuisine && <span>{selectedRecipe.cuisine} • </span>}
                  {(selectedRecipe.prep_time_minutes || selectedRecipe.cook_time_minutes) && (
                    <span>{(selectedRecipe.prep_time_minutes || 0) + (selectedRecipe.cook_time_minutes || 0)} min</span>
                  )}
                </div>
              </div>
              <div className="flex gap-2">
                {onOpenFocus && (
                  <button
                    onClick={() => onOpenFocus({ type: 'recipe', id: selectedRecipe.id })}
                    className="px-3 py-1 text-sm text-[var(--color-accent)] hover:underline"
                  >
                    View
                  </button>
                )}
                <button
                  onClick={() => setShowRecipeSelector(true)}
                  className="px-3 py-1 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                >
                  Change
                </button>
              </div>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowRecipeSelector(true)}
            className="w-full py-4 bg-[var(--color-bg-secondary)] border-2 border-dashed border-[var(--color-border)] rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors"
          >
            + Assign a Recipe
          </button>
        )}
      </div>

      {/* Notes */}
      {mealPlan.notes && (
        <div className="mb-6">
          <h2 className="text-sm font-medium text-[var(--color-text-muted)] mb-1">
            Notes
          </h2>
          <p className="text-[var(--color-text-primary)]">{mealPlan.notes}</p>
        </div>
      )}

      {/* Servings */}
      {mealPlan.servings && (
        <div className="mb-6">
          <h2 className="text-sm font-medium text-[var(--color-text-muted)] mb-1">
            Servings
          </h2>
          <p className="text-[var(--color-text-primary)]">{mealPlan.servings}</p>
        </div>
      )}

      {/* Hint for empty state */}
      {!selectedRecipe && recipes.length === 0 && (
        <div className="mt-8 p-4 bg-[var(--color-accent-muted)] rounded-[var(--radius-md)] text-center">
          <p className="text-[var(--color-accent)] text-sm">
            💡 <strong>Tip:</strong> Go to Chat and ask Alfred to create a recipe for this meal!
          </p>
        </div>
      )}

      {saving && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50">
          <div className="bg-[var(--color-bg-secondary)] px-6 py-4 rounded-[var(--radius-md)] text-[var(--color-text-primary)]">
            Saving...
          </div>
        </div>
      )}
    </div>
  )
}
