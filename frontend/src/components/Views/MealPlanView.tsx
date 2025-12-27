import { useEffect, useState } from 'react'

interface MealPlan {
  id: string
  date: string
  meal_type: string
  recipe_id: string | null
  notes: string | null
  servings: number | null
}

interface MealPlanViewProps {
  onOpenFocus: (item: { type: string; id: string }) => void
}

export function MealPlanView({ onOpenFocus }: MealPlanViewProps) {
  const [mealPlans, setMealPlans] = useState<MealPlan[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchMealPlans()
  }, [])

  const fetchMealPlans = async () => {
    try {
      const res = await fetch('/api/tables/meal_plans', { credentials: 'include' })
      const data = await res.json()
      setMealPlans(data.data || [])
    } catch (err) {
      console.error('Failed to fetch meal plans:', err)
    } finally {
      setLoading(false)
    }
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
              {new Date(date).toLocaleDateString('en-US', {
                weekday: 'long',
                month: 'short',
                day: 'numeric',
              })}
            </h2>
            <div className="space-y-2">
              {plans.map((plan) => (
                <button
                  key={plan.id}
                  onClick={() => onOpenFocus({ type: 'meal_plan', id: plan.id })}
                  className="w-full text-left bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 hover:border-[var(--color-accent)] transition-colors flex items-center justify-between"
                >
                  <div>
                    <span className="px-2 py-0.5 bg-[var(--color-accent-muted)] text-[var(--color-accent)] rounded-[var(--radius-sm)] text-sm capitalize">
                      {plan.meal_type}
                    </span>
                    <span className="ml-3 text-[var(--color-text-primary)]">
                      {plan.notes || '(No recipe assigned)'}
                    </span>
                  </div>
                  {plan.servings && (
                    <span className="text-sm text-[var(--color-text-muted)]">
                      {plan.servings} servings
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

