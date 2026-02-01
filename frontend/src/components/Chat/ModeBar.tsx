/**
 * ModeBar - Mode switcher + mode indicator displayed above chat input.
 *
 * Plan mode: shows Cook/Brainstorm entry buttons.
 * Cook/Brainstorm mode: shows mode indicator + exit button.
 */

import { useChatContext } from '../../context/ChatContext'

interface ModeBarProps {
  onCookClick: () => void
  onBrainstormClick: () => void
  onSendExit: (exitMsg: string) => void
  disabled?: boolean
}

export function ModeBar({ onCookClick, onBrainstormClick, onSendExit, disabled }: ModeBarProps) {
  const { activeMode, cookRecipeName } = useChatContext()

  if (activeMode === 'cook') {
    return (
      <div className="flex items-center justify-between mb-2 px-3 py-2 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)]">
        <span className="text-sm text-[var(--color-text-primary)] font-medium">
          Cooking: {cookRecipeName || 'Recipe'}
        </span>
        <button
          type="button"
          onClick={() => onSendExit('__cook_exit__')}
          disabled={disabled}
          className="px-3 py-1 text-sm rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-accent)] hover:text-[var(--color-text-inverse)] transition-colors disabled:opacity-50"
        >
          Exit Cook
        </button>
      </div>
    )
  }

  if (activeMode === 'brainstorm') {
    return (
      <div className="flex items-center justify-between mb-2 px-3 py-2 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)]">
        <span className="text-sm text-[var(--color-text-primary)] font-medium">
          Brainstorming
        </span>
        <button
          type="button"
          onClick={() => onSendExit('__brainstorm_exit__')}
          disabled={disabled}
          className="px-3 py-1 text-sm rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-accent)] hover:text-[var(--color-text-inverse)] transition-colors disabled:opacity-50"
        >
          Exit Brainstorm
        </button>
      </div>
    )
  }

  // Plan/Quick mode: show mode entry buttons
  return (
    <div className="flex items-center gap-2 mb-2">
      <button
        type="button"
        onClick={onCookClick}
        disabled={disabled}
        className="px-3 py-1.5 text-sm rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors disabled:opacity-50"
      >
        Cook
      </button>
      <button
        type="button"
        onClick={onBrainstormClick}
        disabled={disabled}
        className="px-3 py-1.5 text-sm rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors disabled:opacity-50"
      >
        Brainstorm
      </button>
    </div>
  )
}
