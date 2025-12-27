interface EntityCardProps {
  type: string
  count: number
  onClick: () => void
}

const typeConfig: Record<string, { icon: string; label: string }> = {
  inventory: { icon: '📦', label: 'Inventory' },
  shopping_list: { icon: '🛒', label: 'Shopping List' },
  tasks: { icon: '✅', label: 'Tasks' },
  recipe_ingredients: { icon: '🥬', label: 'Ingredients' },
}

export function EntityCard({ type, count, onClick }: EntityCardProps) {
  const config = typeConfig[type] || { icon: '📄', label: type }
  const sign = count > 0 ? '+' : ''

  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-[var(--radius-md)] hover:border-[var(--color-accent)] transition-colors cursor-pointer"
    >
      <span className="text-lg">{config.icon}</span>
      <span className="text-sm text-[var(--color-text-primary)]">
        {config.label}
      </span>
      <span className="text-xs text-[var(--color-text-muted)]">
        ({sign}{count})
      </span>
      <span className="text-[var(--color-text-muted)]">→</span>
    </button>
  )
}

