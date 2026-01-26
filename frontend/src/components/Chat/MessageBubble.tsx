import React from 'react'
import { useNavigate } from 'react-router-dom'
import { MentionCard } from './MentionCard'
import { ActiveContextDisplay } from './ActiveContextDisplay'
import type { ActiveContext, ActiveContextEntity } from '../../types/chat'

// Re-export for consumers
export type { ActiveContext, ActiveContextEntity }

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  activeContext?: ActiveContext
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
