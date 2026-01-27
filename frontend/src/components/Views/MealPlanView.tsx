import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { useUIChanges } from '../../context/ChatContext'
import { EntityFormModal } from '../Form/EntityForm'
import { RecipePicker } from '../Form/pickers'

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
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingPlan, setEditingPlan] = useState<MealPlan | null>(null)
  const { pushUIChange } = useUIChanges()

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      // Fetch meal plans and recipes in parallel
      const [mealData, recipeData] = await Promise.all([
        apiRequest('/api/entities/meal_plans'),
        apiRequest('/api/entities/recipes'),
      ])
      
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

  const getMealPlanLabel = (plan: any): string => {
    // Format: "Jan 15 - Dinner"
    const [year, month, day] = plan.date.split('-').map(Number)
    const date = new Date(year, month - 1, day)
    const formatted = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    const mealType = plan.meal_type.charAt(0).toUpperCase() + plan.meal_type.slice(1)
    return `${formatted} - ${mealType}`
  }

  const handlePlanCreated = (data: any) => {
    setMealPlans((prev) => [...prev, data])
    setShowAddModal(false)
    // Track UI change for AI context
    pushUIChange({
      action: 'created:user',
      entity_type: 'meal',
      id: data.id,
      label: getMealPlanLabel(data),
      data: data,
    })
  }

  const handlePlanUpdated = (data: any) => {
    setMealPlans((prev) => prev.map((p) => (p.id === data.id ? data : p)))
    setEditingPlan(null)
    // Track UI change for AI context
    pushUIChange({
      action: 'updated:user',
      entity_type: 'meal',
      id: data.id,
      label: getMealPlanLabel(data),
      data: data,
    })
  }

  const deletePlan = async (e: React.MouseEvent, plan: MealPlan) => {
    e.stopPropagation()
    if (!confirm(`Delete this meal plan?`)) return

    // Optimistic update
    setMealPlans((prev) => prev.filter((p) => p.id !== plan.id))

    try {
      await apiRequest(`/api/entities/meal_plans/${plan.id}`, {
        method: 'DELETE',
      })
      // Track UI change for AI context
      pushUIChange({
        action: 'deleted:user',
        entity_type: 'meal',
        id: plan.id,
        label: getMealPlanLabel(plan),
      })
    } catch (err) {
      // Revert on error
      setMealPlans((prev) => [...prev, plan])
      console.error('Failed to delete meal plan:', err)
    }
  }

  // Modal components
  const addPlanModal = (
    <EntityFormModal
      title="Add Meal Plan"
      isOpen={showAddModal}
      onClose={() => setShowAddModal(false)}
      subdomain="meal_plans"
      table="meal_plans"
      mode="create"
      onSuccess={handlePlanCreated}
      fieldOrder={['date', 'meal_type', 'recipe_id', 'servings', 'notes']}
      excludeFields={['id', 'user_id', 'created_at']}
      customRenderers={{
        recipe_id: RecipePicker,
      }}
    />
  )

  const editPlanModal = editingPlan && (
    <EntityFormModal
      title="Edit Meal Plan"
      isOpen={!!editingPlan}
      onClose={() => setEditingPlan(null)}
      subdomain="meal_plans"
      table="meal_plans"
      mode="edit"
      entityId={editingPlan.id}
      initialData={editingPlan}
      onSuccess={handlePlanUpdated}
      fieldOrder={['date', 'meal_type', 'recipe_id', 'servings', 'notes']}
      excludeFields={['id', 'user_id', 'created_at']}
      customRenderers={{
        recipe_id: RecipePicker,
      }}
    />
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading meal plans...</div>
      </div>
    )
  }

  if (mealPlans.length === 0) {
    return (
      <>
        <div className="flex flex-col items-center justify-center h-full text-center p-8">
          <span className="text-4xl mb-4">📅</span>
          <h2 className="text-xl text-[var(--color-text-primary)] mb-2">No meal plans yet</h2>
          <p className="text-[var(--color-text-muted)] mb-4">
            Ask Alfred to plan your meals!
          </p>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)]"
          >
            + Add Meal Plan
          </motion.button>
        </div>
        {addPlanModal}
      </>
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
    <>
      <div className="h-full overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
            Meal Plans
          </h1>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)] text-sm"
          >
            + Add Meal Plan
          </motion.button>
        </div>

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
                  <div
                    key={plan.id}
                    className="group flex items-center gap-2 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 hover:border-[var(--color-accent)] transition-colors"
                  >
                    <button
                      onClick={() => onOpenFocus({ type: 'meal_plan', id: plan.id })}
                      className="flex-1 flex items-center justify-between text-left"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="shrink-0 px-2 py-0.5 bg-[var(--color-accent-muted)] text-[var(--color-accent)] rounded-[var(--radius-sm)] text-sm capitalize">
                          {plan.meal_type}
                        </span>
                        <span className="truncate text-[var(--color-text-primary)]">
                          {display.text}
                        </span>
                        {display.isRecipe && (
                          <span
                            onClick={(e) => {
                              e.stopPropagation()
                              onOpenFocus({ type: 'recipe', id: display.recipeId! })
                            }}
                            className="shrink-0 text-xs text-[var(--color-accent)] hover:underline cursor-pointer"
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
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditingPlan(plan)
                      }}
                      className="md:opacity-0 md:group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-opacity px-2"
                      title="Edit"
                    >
                      ✏️
                    </button>
                    <button
                      onClick={(e) => deletePlan(e, plan)}
                      className="md:opacity-0 md:group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-opacity px-2"
                      title="Delete"
                    >
                      🗑️
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      </div>
      {addPlanModal}
      {editPlanModal}
    </>
  )
}
