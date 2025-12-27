import { useEffect, useState } from 'react'

interface Recipe {
  id: string
  name: string
  cuisine: string | null
  difficulty: string | null
  prep_time_minutes: number | null
  cook_time_minutes: number | null
  servings: number | null
  tags: string[] | null
  created_at: string
}

interface RecipesViewProps {
  onOpenFocus: (item: { type: string; id: string }) => void
}

export function RecipesView({ onOpenFocus }: RecipesViewProps) {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchRecipes()
  }, [])

  const fetchRecipes = async () => {
    try {
      const res = await fetch('/api/tables/recipes', { credentials: 'include' })
      const data = await res.json()
      setRecipes(data.data || [])
    } catch (err) {
      console.error('Failed to fetch recipes:', err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading recipes...</div>
      </div>
    )
  }

  if (recipes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <span className="text-4xl mb-4">🍳</span>
        <h2 className="text-xl text-[var(--color-text-primary)] mb-2">No recipes yet</h2>
        <p className="text-[var(--color-text-muted)]">
          Ask Alfred to create some recipes for you!
        </p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text-primary)] mb-6">
        Recipes
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {recipes.map((recipe) => (
          <button
            key={recipe.id}
            onClick={() => onOpenFocus({ type: 'recipe', id: recipe.id })}
            className="text-left bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 hover:border-[var(--color-accent)] transition-colors"
          >
            <h3 className="font-medium text-[var(--color-text-primary)] mb-2">
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
        ))}
      </div>
    </div>
  )
}

