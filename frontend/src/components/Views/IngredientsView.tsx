import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface Ingredient {
  id: string
  name: string
  aliases: string[] | null
  default_unit: string | null
}

interface CategoryInfo {
  category: string
}

export function IngredientsView() {
  const [categories, setCategories] = useState<CategoryInfo[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null)
  const [categoryIngredients, setCategoryIngredients] = useState<Record<string, Ingredient[]>>({})
  const [loadingCategory, setLoadingCategory] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [searchResults, setSearchResults] = useState<(Ingredient & { category: string })[]>([])
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    fetchCategories()
  }, [])

  // Debounced search
  useEffect(() => {
    if (!searchTerm) {
      setSearchResults([])
      return
    }
    
    const timer = setTimeout(() => {
      searchIngredients(searchTerm)
    }, 300)
    
    return () => clearTimeout(timer)
  }, [searchTerm])

  const fetchCategories = async () => {
    try {
      const res = await fetch('/api/ingredients/categories', { credentials: 'include' })
      const data = await res.json()
      setCategories(data.data || [])
      setTotalCount(data.total || 0)
    } catch (err) {
      console.error('Failed to fetch categories:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchCategoryIngredients = async (category: string) => {
    if (categoryIngredients[category]) return // Already loaded
    
    setLoadingCategory(category)
    try {
      const res = await fetch(`/api/ingredients/by-category/${encodeURIComponent(category)}`, { credentials: 'include' })
      const data = await res.json()
      setCategoryIngredients(prev => ({ ...prev, [category]: data.data || [] }))
    } catch (err) {
      console.error('Failed to fetch ingredients for category:', err)
    } finally {
      setLoadingCategory(null)
    }
  }

  const searchIngredients = async (query: string) => {
    setSearching(true)
    try {
      const res = await fetch(`/api/ingredients/search?q=${encodeURIComponent(query)}`, { credentials: 'include' })
      const data = await res.json()
      setSearchResults(data.data || [])
    } catch (err) {
      console.error('Failed to search ingredients:', err)
    } finally {
      setSearching(false)
    }
  }

  const handleCategoryClick = (category: string) => {
    if (expandedCategory === category) {
      setExpandedCategory(null)
    } else {
      setExpandedCategory(category)
      fetchCategoryIngredients(category)
    }
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-[var(--color-text-secondary)]">Loading categories...</div>
      </div>
    )
  }

  const isSearching = searchTerm.length > 0

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-6 border-b border-[var(--color-border)]">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-light text-[var(--color-text-primary)]">
              Ingredients Database
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)] mt-1">
              {totalCount.toLocaleString()} ingredients across {categories.length} categories
            </p>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <input
            type="text"
            placeholder="Search ingredients..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full px-4 py-2 pl-10 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">
            🔍
          </span>
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {isSearching ? (
          // Search Results
          <div>
            {searching ? (
              <div className="text-center text-[var(--color-text-secondary)] py-4">
                Searching...
              </div>
            ) : searchResults.length === 0 ? (
              <div className="text-center text-[var(--color-text-secondary)] py-8">
                No ingredients found matching "{searchTerm}"
              </div>
            ) : (
              <div className="space-y-1">
                <div className="text-sm text-[var(--color-text-secondary)] mb-3">
                  {searchResults.length} results (showing first 50)
                </div>
                {searchResults.map(ing => (
                  <div
                    key={ing.id}
                    className="px-4 py-2 flex items-center justify-between bg-[var(--color-bg-secondary)] rounded-[var(--radius-sm)] hover:bg-[var(--color-bg-tertiary)]"
                  >
                    <div>
                      <span className="text-[var(--color-text-primary)]">
                        {ing.name}
                      </span>
                      <span className="ml-2 text-xs text-[var(--color-accent)] bg-[var(--color-accent-muted)] px-2 py-0.5 rounded capitalize">
                        {ing.category || 'uncategorized'}
                      </span>
                      {ing.aliases && ing.aliases.length > 0 && (
                        <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                          ({ing.aliases.slice(0, 2).join(', ')})
                        </span>
                      )}
                    </div>
                    {ing.default_unit && (
                      <span className="text-xs text-[var(--color-text-secondary)]">
                        {ing.default_unit}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          // Category List
          <div className="space-y-2">
            {categories.map(cat => (
              <div key={cat.category} className="border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden">
                {/* Category Header */}
                <button
                  onClick={() => handleCategoryClick(cat.category)}
                  className="w-full flex items-center justify-between px-4 py-3 bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-lg">
                      {getCategoryIcon(cat.category)}
                    </span>
                    <span className="font-medium text-[var(--color-text-primary)] capitalize">
                      {cat.category}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    {categoryIngredients[cat.category] && (
                      <span className="text-sm text-[var(--color-text-secondary)]">
                        {categoryIngredients[cat.category].length}
                      </span>
                    )}
                    <span className={`text-[var(--color-text-muted)] transition-transform ${
                      expandedCategory === cat.category ? 'rotate-180' : ''
                    }`}>
                      ▼
                    </span>
                  </div>
                </button>

                {/* Ingredients List (lazy loaded) */}
                <AnimatePresence>
                  {expandedCategory === cat.category && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      {loadingCategory === cat.category ? (
                        <div className="px-4 py-3 text-center text-[var(--color-text-secondary)]">
                          Loading...
                        </div>
                      ) : (
                        <div className="divide-y divide-[var(--color-border)] max-h-80 overflow-auto">
                          {(categoryIngredients[cat.category] || []).map(ing => (
                            <div
                              key={ing.id}
                              className="px-4 py-2 flex items-center justify-between hover:bg-[var(--color-bg-tertiary)]"
                            >
                              <div>
                                <span className="text-[var(--color-text-primary)]">
                                  {ing.name}
                                </span>
                                {ing.aliases && ing.aliases.length > 0 && (
                                  <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                                    ({ing.aliases.slice(0, 3).join(', ')}{ing.aliases.length > 3 ? '...' : ''})
                                  </span>
                                )}
                              </div>
                              {ing.default_unit && (
                                <span className="text-xs text-[var(--color-text-secondary)] bg-[var(--color-bg-tertiary)] px-2 py-1 rounded">
                                  {ing.default_unit}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function getCategoryIcon(category: string): string {
  const icons: Record<string, string> = {
    'produce': '🥬',
    'vegetables': '🥕',
    'fruits': '🍎',
    'meat': '🥩',
    'poultry': '🍗',
    'seafood': '🐟',
    'dairy': '🧀',
    'eggs': '🥚',
    'grains': '🌾',
    'bread': '🍞',
    'pasta': '🍝',
    'rice': '🍚',
    'legumes': '🫘',
    'beans': '🫘',
    'nuts': '🥜',
    'seeds': '🌻',
    'spices': '🌶️',
    'herbs': '🌿',
    'condiments': '🍯',
    'sauces': '🥫',
    'oils': '🫒',
    'vinegars': '🍶',
    'baking': '🧁',
    'sweeteners': '🍯',
    'canned': '🥫',
    'frozen': '🧊',
    'beverages': '🥤',
    'snacks': '🍿',
    'international': '🌍',
    'asian': '🥢',
    'mexican': '🌮',
    'indian': '🍛',
    'italian': '🍕',
    'mediterranean': '🫒',
    'uncategorized': '📦',
  }
  return icons[category.toLowerCase()] || '📦'
}
