import React from 'react'
import { useNavigate } from 'react-router-dom'
import { MentionCard } from './MentionCard'
import { EntityCard } from './EntityCard'

export interface Entity {
  type: string
  id: string
  name: string
  action?: string
  state?: 'pending' | 'active' // V3 entity state
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  entities?: Entity[]
}

interface MessageBubbleProps {
  message: Message
  onOpenFocus: (item: { type: string; id: string }) => void
}

// Parse inline mentions: @[Label](type:id)
const MENTION_REGEX = /@\[([^\]]+)\]\((recipe|inv|shop|task):([a-zA-Z0-9-]+)\)/g

function parseContent(content: string, onOpenFocus: (item: { type: string; id: string }) => void) {
  const parts: (string | React.ReactNode)[] = []
  let lastIndex = 0
  let match

  const regex = new RegExp(MENTION_REGEX)
  while ((match = regex.exec(content)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index))
    }

    // Add inline mention
    const [, label, type, id] = match
    parts.push(
      <MentionCard
        key={`${type}-${id}-${match.index}`}
        type={type}
        id={id}
        label={label}
        inline
        onClick={() => onOpenFocus({ type, id })}
      />
    )

    lastIndex = match.index + match[0].length
  }

  // Add remaining text
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex))
  }

  return parts.length > 0 ? parts : [content]
}

// V3: Entity state badge component
function EntityBadge({ entity, onOpenFocus }: { entity: Entity; onOpenFocus: (item: { type: string; id: string }) => void }) {
  const isPending = entity.state === 'pending'
  
  // Route mapping for clickable entities
  const isClickable = ['recipes', 'meal_plans'].includes(entity.type)
  const focusType = entity.type === 'recipes' ? 'recipe' : entity.type === 'meal_plans' ? 'meal_plan' : entity.type
  
  return (
    <span
      onClick={isClickable ? () => onOpenFocus({ type: focusType, id: entity.id }) : undefined}
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-[var(--radius-sm)] text-xs ${
        isPending
          ? 'bg-amber-500/10 border border-dashed border-amber-500/50 text-amber-400'
          : 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
      } ${isClickable ? 'cursor-pointer hover:opacity-80' : ''}`}
    >
      <span className="font-medium">{entity.name}</span>
      <span className={`text-[10px] uppercase tracking-wide ${isPending ? 'text-amber-500/70' : 'text-emerald-500/70'}`}>
        {isPending ? 'proposed' : 'saved'}
      </span>
    </span>
  )
}

export function MessageBubble({ message, onOpenFocus }: MessageBubbleProps) {
  const navigate = useNavigate()
  const isUser = message.role === 'user'

  // V3: Separate entities with state (for badges) vs without (for aggregate cards)
  const entitiesWithState = message.entities?.filter(e => e.state) || []
  const entitiesWithoutState = message.entities?.filter(e => !e.state) || []

  // Filter entities for aggregate cards (legacy behavior)
  // Exclude: recipes, meal_plans (inline mentions), recipe_ingredients (internal to recipes)
  const aggregateEntities = entitiesWithoutState?.filter(
    (e) => !['recipes', 'meal_plans', 'recipe_ingredients'].includes(e.type)
  )

  // Dedupe by type for aggregate display
  const entityCounts = aggregateEntities?.reduce((acc, e) => {
    acc[e.type] = (acc[e.type] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] ${
          isUser
            ? 'bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded-2xl rounded-br-sm'
            : 'bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl rounded-bl-sm'
        } px-4 py-3`}
      >
        {/* Sender label */}
        <div
          className={`text-xs mb-1 ${
            isUser ? 'text-[var(--color-text-inverse)]/70' : 'text-[var(--color-text-muted)]'
          }`}
        >
          {isUser ? 'You' : 'Alfred'}
        </div>

        {/* Content with parsed mentions */}
        <div className="text-sm leading-relaxed whitespace-pre-wrap">
          {parseContent(message.content, onOpenFocus)}
        </div>

        {/* V3: Entity state badges */}
        {entitiesWithState.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {entitiesWithState.map((entity, i) => (
              <EntityBadge key={`${entity.id}-${i}`} entity={entity} onOpenFocus={onOpenFocus} />
            ))}
          </div>
        )}

        {/* Aggregate entity cards (legacy) */}
        {entityCounts && Object.keys(entityCounts).length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {Object.entries(entityCounts).map(([type, count]) => (
              <EntityCard
                key={type}
                type={type}
                count={count}
                onClick={() => {
                  // Navigate to the appropriate view
                  const routes: Record<string, string> = {
                    inventory: '/inventory',
                    shopping_list: '/shopping',
                    tasks: '/tasks',
                  }
                  if (routes[type]) {
                    navigate(routes[type])
                  }
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
