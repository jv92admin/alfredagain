interface MentionCardProps {
  type: string
  id: string
  label: string
  inline?: boolean
  onClick: () => void
}

const typeIcons: Record<string, string> = {
  recipe: '🍳',
  recipes: '🍳',
  inv: '📦',
  inventory: '📦',
  shop: '🛒',
  shopping_list: '🛒',
  task: '✅',
  tasks: '✅',
}

export function MentionCard({ type, label, inline, onClick }: MentionCardProps) {
  const icon = typeIcons[type] || '📄'

  if (inline) {
    // Inline chip style
    return (
      <button
        onClick={onClick}
        className="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded-[var(--radius-sm)] text-sm font-medium hover:opacity-80 transition-colors cursor-pointer mx-0.5"
      >
        <span>{icon}</span>
        <span>{label}</span>
      </button>
    )
  }

  // Block card style
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-[var(--radius-md)] hover:border-[var(--color-accent)] transition-colors cursor-pointer"
    >
      <span className="text-lg">{icon}</span>
      <span className="text-sm text-[var(--color-text-primary)]">{label}</span>
    </button>
  )
}

