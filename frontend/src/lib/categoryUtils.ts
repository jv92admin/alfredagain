/**
 * Shared category utilities for ingredient-linked views.
 */

export function getCategoryIcon(category: string): string {
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

/**
 * Groups items by category, sorted by count descending. "other" always last.
 */
export function groupByCategory<T extends { category?: string | null }>(
  items: T[]
): [string, T[]][] {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const key = item.category || 'other'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }
  return [...groups.entries()].sort((a, b) => {
    if (a[0] === 'other') return 1
    if (b[0] === 'other') return -1
    return b[1].length - a[1].length
  })
}
