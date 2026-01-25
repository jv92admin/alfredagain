/**
 * MealPlanPicker - Date-grouped dropdown for selecting a meal plan.
 *
 * Used for FK fields like meal_plan_id in Task forms.
 * Fetches meal plans from /api/entities/meal_plans and displays them
 * grouped by date with meal_type badge.
 */

import { useState, useEffect, useRef } from 'react'
import { apiRequest } from '../../../lib/api'
import type { FieldRendererProps } from '../FieldRenderer'

interface MealPlan {
  id: string
  date: string
  meal_type: string
  recipe_id: string | null
  notes: string | null
}

interface Recipe {
  id: string
  name: string
}

export function MealPlanPicker({
  name,
  label,
  value,
  onChange,
  required,
  error,
  disabled,
}: FieldRendererProps) {
  const [mealPlans, setMealPlans] = useState<MealPlan[]>([])
  const [recipes, setRecipes] = useState<Record<string, Recipe>>({})
  const [loading, setLoading] = useState(true)
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch meal plans and recipes on mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [mealData, recipeData] = await Promise.all([
          apiRequest('/api/entities/meal_plans'),
          apiRequest('/api/entities/recipes'),
        ])

        setMealPlans(mealData.data || [])

        // Build recipe lookup map
        const recipeMap: Record<string, Recipe> = {}
        for (const recipe of recipeData.data || []) {
          recipeMap[recipe.id] = recipe
        }
        setRecipes(recipeMap)
      } catch (err) {
        console.error('Failed to fetch meal plans:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
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

  // Group meal plans by date
  const groupedByDate = mealPlans.reduce((acc, plan) => {
    if (!acc[plan.date]) acc[plan.date] = []
    acc[plan.date].push(plan)
    return acc
  }, {} as Record<string, MealPlan[]>)

  // Sort dates (most recent first)
  const sortedDates = Object.keys(groupedByDate).sort((a, b) => b.localeCompare(a))

  // Get selected meal plan
  const selectedPlan = mealPlans.find((p) => p.id === value)

  const handleSelect = (planId: string | null) => {
    onChange(planId)
    setIsOpen(false)
  }

  const formatDate = (dateStr: string) => {
    const [year, month, day] = dateStr.split('-').map(Number)
    return new Date(year, month - 1, day).toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    })
  }

  const getMealPlanLabel = (plan: MealPlan) => {
    if (plan.recipe_id && recipes[plan.recipe_id]) {
      return recipes[plan.recipe_id].name
    }
    if (plan.notes) {
      return plan.notes.slice(0, 30) + (plan.notes.length > 30 ? '...' : '')
    }
    return '(No meal assigned)'
  }

  const formatLabel = (str: string) =>
    str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  const getMealTypeColor = (mealType: string) => {
    switch (mealType.toLowerCase()) {
      case 'breakfast': return 'bg-amber-500/10 text-amber-600'
      case 'lunch': return 'bg-green-500/10 text-green-600'
      case 'dinner': return 'bg-blue-500/10 text-blue-600'
      case 'snack': return 'bg-purple-500/10 text-purple-600'
      default: return 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]'
    }
  }

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
          ) : selectedPlan ? (
            <span className="flex items-center gap-2">
              <span className={`px-2 py-0.5 text-xs rounded-full capitalize ${getMealTypeColor(selectedPlan.meal_type)}`}>
                {selectedPlan.meal_type}
              </span>
              <span>{formatDate(selectedPlan.date)}</span>
              <span className="text-[var(--color-text-muted)]">-</span>
              <span className="truncate">{getMealPlanLabel(selectedPlan)}</span>
            </span>
          ) : (
            <span className="text-[var(--color-text-muted)]">Select a meal plan...</span>
          )}
          <span className="text-[var(--color-text-muted)]">
            {isOpen ? '▲' : '▼'}
          </span>
        </button>

        {/* Dropdown */}
        {isOpen && (
          <div className="absolute z-50 w-full mt-1 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-lg max-h-72 overflow-hidden">
            {/* Options */}
            <div className="overflow-y-auto max-h-64">
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

              {sortedDates.length === 0 ? (
                <div className="px-3 py-4 text-center text-[var(--color-text-muted)] text-sm">
                  No meal plans available
                </div>
              ) : (
                sortedDates.map((date) => (
                  <div key={date}>
                    {/* Date header */}
                    <div className="px-3 py-1.5 bg-[var(--color-bg-tertiary)] text-xs font-medium text-[var(--color-text-muted)] sticky top-0">
                      {formatDate(date)}
                    </div>

                    {/* Meal plans for this date */}
                    {groupedByDate[date].map((plan) => (
                      <button
                        key={plan.id}
                        type="button"
                        onClick={() => handleSelect(plan.id)}
                        className={`
                          w-full px-3 py-2 text-left flex items-center gap-2
                          hover:bg-[var(--color-bg-tertiary)] transition-colors
                          ${plan.id === value ? 'bg-[var(--color-accent-muted)]' : ''}
                        `}
                      >
                        <span className={`px-2 py-0.5 text-xs rounded-full capitalize ${getMealTypeColor(plan.meal_type)}`}>
                          {plan.meal_type}
                        </span>
                        <span className="flex-1 text-[var(--color-text-primary)] truncate">
                          {getMealPlanLabel(plan)}
                        </span>
                      </button>
                    ))}
                  </div>
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
