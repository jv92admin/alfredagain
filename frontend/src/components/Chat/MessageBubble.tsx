import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MentionCard } from './MentionCard'
import { ActiveContextDisplay } from './ActiveContextDisplay'
import { StreamingProgress, type PhaseState } from './StreamingProgress'
import type { ActiveContext, ActiveContextEntity } from '../../types/chat'

// Re-export for consumers
export type { ActiveContext, ActiveContextEntity }

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  activeContext?: ActiveContext
  reasoning?: PhaseState
}

interface MessageBubbleProps {
  message: Message
  onOpenFocus: (item: { type: string; id: string }) => void
}

// Collapsible reasoning trace component
function CollapsibleReasoning({ reasoning }: { reasoning: PhaseState }) {
  const [expanded, setExpanded] = useState(false)

  const completedSteps = reasoning.steps.filter((s) => s && s.status === 'completed').length

  return (
    <div className="mt-2 border-t border-[var(--color-border)] pt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
      >
        <span>{expanded ? '▼' : '▶'}</span>
        <span>{expanded ? 'Hide' : 'Show'} reasoning</span>
        <span className="opacity-60">({completedSteps} steps completed)</span>
      </button>

      {expanded && (
        <div className="mt-2">
          <StreamingProgress phase={reasoning} mode="plan" />
        </div>
      )}
    </div>
  )
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

export function MessageBubble({ message, onOpenFocus }: MessageBubbleProps) {
  const navigate = useNavigate()
  const isUser = message.role === 'user'

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

        {/* Collapsible reasoning trace - only show when there were actual steps */}
        {!isUser && message.reasoning && message.reasoning.steps.length > 0 && (
          <CollapsibleReasoning reasoning={message.reasoning} />
        )}

        {/* V10: Active context display */}
        {!isUser && message.activeContext && (
          <ActiveContextDisplay
            context={message.activeContext}
            defaultExpanded={false}
            onEntityClick={(entity) => {
              // Navigate based on entity type
              const typeRoutes: Record<string, string> = {
                recipe: '/recipes',
                recipes: '/recipes',
                inventory: '/inventory',
                inv: '/inventory',
                shopping_list: '/shopping',
                shop: '/shopping',
                meal_plans: '/meals',
                meal: '/meals',
                tasks: '/tasks',
                task: '/tasks',
              }
              const route = typeRoutes[entity.type]
              if (route) {
                navigate(route)
              }
            }}
          />
        )}
      </div>
    </div>
  )
}
