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
}

interface MealPlanViewProps {
  onOpenFocus: (item: { type: string; id: string }) => void
}

export function MealPlanView({ onOpenFocus }: MealPlanViewProps) {
  const [mealPlans, setMealPlans] = useState<MealPlan[]>([])
  const [recipes, setRecipes] = useState<Record<string, Recipe>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      // Fetch meal plans and recipes in parallel
      const [mealRes, recipeRes] = await Promise.all([
        fetch('/api/tables/meal_plans', { credentials: 'include' }),
        fetch('/api/tables/recipes', { credentials: 'include' }),
      ])
      
      const mealData = await mealRes.json()
      const recipeData = await recipeRes.json()
      
      setMealPlans(mealData.data || [])
      
      // Build recipe lookup map by ID
      const recipeMap: Record<string, Recipe> = {}
      for (const recipe of recipeData.data || []) {
        recipeMap[recipe.id] = recipe
      }
      setRecipes(recipeMap)
    } catch (err) {
      console.error('Failed to fetch data:', err)
    } finally {
      setLoading(false)
    }
  }

  const getDisplayName = (plan: MealPlan): { text: string; isRecipe: boolean; recipeId?: string } => {
    if (plan.recipe_id && recipes[plan.recipe_id]) {
      return { text: recipes[plan.recipe_id].name, isRecipe: true, recipeId: plan.recipe_id }
    }
    if (plan.notes) {
      return { text: plan.notes, isRecipe: false }
    }
    return { text: '(No meal assigned)', isRecipe: false }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading meal plans...</div>
      </div>
    )
  }

  if (mealPlans.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <span className="text-4xl mb-4">📅</span>
        <h2 className="text-xl text-[var(--color-text-primary)] mb-2">No meal plans yet</h2>
        <p className="text-[var(--color-text-muted)]">
          Ask Alfred to plan your meals!
        </p>
      </div>
    )
  }

  // Group by date
  const groupedByDate = mealPlans.reduce((acc, plan) => {
    const date = plan.date
    if (!acc[date]) acc[date] = []
    acc[date].push(plan)
    return acc
  }, {} as Record<string, MealPlan[]>)

  return (
    <div className="h-full overflow-y-auto p-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text-primary)] mb-6">
        Meal Plans
      </h1>

      <div className="space-y-6">
        {Object.entries(groupedByDate).map(([date, plans]) => (
          <div key={date}>
            <h2 className="text-lg font-medium text-[var(--color-text-secondary)] mb-3">
              {/* Parse as local date to avoid timezone shift */}
              {(() => {
                const [year, month, day] = date.split('-').map(Number)
                return new Date(year, month - 1, day).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'short',
                  day: 'numeric',
                })
              })()}
            </h2>
            <div className="space-y-2">
              {plans.map((plan) => {
                const display = getDisplayName(plan)
                return (
                  <button
                    key={plan.id}
                    onClick={() => onOpenFocus({ type: 'meal_plan', id: plan.id })}
                    className="w-full text-left bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 hover:border-[var(--color-accent)] transition-colors flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-0.5 bg-[var(--color-accent-muted)] text-[var(--color-accent)] rounded-[var(--radius-sm)] text-sm capitalize">
                        {plan.meal_type}
                      </span>
                      <span className="text-[var(--color-text-primary)]">
                        {display.text}
                      </span>
                      {display.isRecipe && (
                        <span
                          onClick={(e) => {
                            e.stopPropagation()
                            onOpenFocus({ type: 'recipe', id: display.recipeId! })
                          }}
                          className="text-xs text-[var(--color-accent)] hover:underline cursor-pointer"
                        >
                          View Recipe →
                        </span>
                      )}
                    </div>
                    {plan.servings && (
                      <span className="text-sm text-[var(--color-text-muted)]">
                        {plan.servings} servings
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
