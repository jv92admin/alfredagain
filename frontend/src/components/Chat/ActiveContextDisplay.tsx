import { useState } from 'react'
import type { ActiveContext, ActiveContextEntity } from '../../types/chat'

interface ActiveContextDisplayProps {
  context: ActiveContext
  defaultExpanded?: boolean
  onEntityClick?: (entity: ActiveContextEntity) => void
}

// Type icons for entity display
const TYPE_ICONS: Record<string, string> = {
  recipe: '🍳',
  recipes: '🍳',
  inventory: '📦',
  inv: '📦',
  shopping_list: '🛒',
  shop: '🛒',
  meal_plans: '📅',
  meal: '📅',
  tasks: '✅',
  task: '✅',
  preferences: '⚙️',
  pref: '⚙️',
  ingredients: '🧂',
  ing: '🧂',
}

// Action styling
const ACTION_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  read: { bg: 'bg-slate-500/10', text: 'text-slate-400', label: 'read' },
  created: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', label: 'created' },
  generated: { bg: 'bg-amber-500/10', text: 'text-amber-400', label: 'proposed' },
  linked: { bg: 'bg-blue-500/10', text: 'text-blue-400', label: 'linked' },
  updated: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', label: 'updated' },
  'mentioned:user': { bg: 'bg-purple-500/10', text: 'text-purple-400', label: 'mentioned' },
  'created:user': { bg: 'bg-emerald-500/10', text: 'text-emerald-400', label: 'created' },
  'updated:user': { bg: 'bg-cyan-500/10', text: 'text-cyan-400', label: 'updated' },
}

function EntityChip({
  entity,
  isNew,
  onClick,
}: {
  entity: ActiveContextEntity
  isNew: boolean
  onClick?: () => void
}) {
  const icon = TYPE_ICONS[entity.type] || '📄'
  const style = ACTION_STYLES[entity.action] || ACTION_STYLES.read

  return (
    <button
      onClick={onClick}
      className={`
        inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs
        ${style.bg} ${style.text}
        hover:opacity-80 transition-opacity
        ${isNew ? 'ring-1 ring-blue-400/50 animate-pulse' : ''}
      `}
    >
      <span>{icon}</span>
      <span className="font-medium max-w-[120px] truncate">{entity.label}</span>
      <span className="text-[10px] uppercase tracking-wide opacity-70">{style.label}</span>
      {isNew && <span className="text-blue-400 text-[10px]">new</span>}
    </button>
  )
}

export function ActiveContextDisplay({
  context,
  defaultExpanded = false,
  onEntityClick,
}: ActiveContextDisplayProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  if (!context || context.entities.length === 0) {
    return null
  }

  const newRefs = new Set(context.changes?.added || [])

  return (
    <div className="mt-2 mb-1 text-xs">
      {/* Collapsible header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
      >
        <span className="text-[10px]">{expanded ? '▼' : '▶'}</span>
        <span>AI Context</span>
        <span className="opacity-60">(Turn {context.currentTurn})</span>
        <span className="opacity-40">• {context.entities.length} entities</span>
        {newRefs.size > 0 && (
          <span className="text-blue-400">+{newRefs.size} new</span>
        )}
      </button>

      {/* Entity list */}
      {expanded && (
        <div className="mt-2 flex flex-wrap gap-1.5 pl-4">
          {context.entities.map((entity) => (
            <EntityChip
              key={entity.ref}
              entity={entity}
              isNew={newRefs.has(entity.ref)}
              onClick={onEntityClick ? () => onEntityClick(entity) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  )
}
