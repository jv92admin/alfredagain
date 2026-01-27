import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
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

// Entity summarization config
const SUMMARIZE_TYPES = ['inventory', 'inv', 'shopping_list', 'shop', 'ingredients', 'ing']
const SUMMARY_THRESHOLD = 5

// Routes for summarized entity types
const TYPE_ROUTES: Record<string, string> = {
  inventory: '/inventory',
  inv: '/inventory',
  shopping_list: '/shopping',
  shop: '/shopping',
  ingredients: '/inventory',
  ing: '/inventory',
}

// Display names for summarized types
const TYPE_DISPLAY_NAMES: Record<string, string> = {
  inventory: 'Inventory',
  inv: 'Inventory',
  shopping_list: 'Shopping List',
  shop: 'Shopping List',
  ingredients: 'Ingredients',
  ing: 'Ingredients',
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

function SummaryChip({
  type,
  count,
  onClick,
}: {
  type: string
  count: number
  onClick: () => void
}) {
  const icon = TYPE_ICONS[type] || '📄'
  const displayName = TYPE_DISPLAY_NAMES[type] || type

  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs bg-slate-500/10 text-slate-400 hover:opacity-80 transition-opacity"
    >
      <span>{icon}</span>
      <span className="font-medium">{displayName} ({count} items)</span>
      <span className="text-[10px] opacity-60">→ VIEW</span>
    </button>
  )
}

export function ActiveContextDisplay({
  context,
  defaultExpanded = false,
  onEntityClick,
}: ActiveContextDisplayProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const navigate = useNavigate()

  // Group entities into summarized (bulk) vs individual
  const { summarized, individual } = useMemo(() => {
    const groups: Record<string, ActiveContextEntity[]> = {}

    for (const entity of context.entities) {
      const key = entity.type
      if (!groups[key]) groups[key] = []
      groups[key].push(entity)
    }

    const summarized: { type: string; count: number; entities: ActiveContextEntity[] }[] = []
    const individual: ActiveContextEntity[] = []

    for (const [type, entities] of Object.entries(groups)) {
      if (SUMMARIZE_TYPES.includes(type) && entities.length > SUMMARY_THRESHOLD) {
        summarized.push({ type, count: entities.length, entities })
      } else {
        individual.push(...entities)
      }
    }

    return { summarized, individual }
  }, [context.entities])

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
          {/* Summarized entity groups first */}
          {summarized.map(({ type, count }) => (
            <SummaryChip
              key={`summary-${type}`}
              type={type}
              count={count}
              onClick={() => {
                const route = TYPE_ROUTES[type]
                if (route) navigate(route)
              }}
            />
          ))}
          {/* Individual entity chips */}
          {individual.map((entity) => (
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
