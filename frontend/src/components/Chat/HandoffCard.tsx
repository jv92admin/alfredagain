/**
 * HandoffCard - Displays handoff summary when exiting Cook/Brainstorm mode.
 *
 * Shows the LLM-generated session summary and action recommendation.
 */

interface HandoffCardProps {
  summary: string
  action: 'save' | 'update' | 'close'
  actionDetail: string
  recipeContent: string | null
  onDismiss: () => void
}

const ACTION_LABELS: Record<string, string> = {
  save: 'Saved to conversation',
  update: 'Notes saved',
  close: 'Session closed',
}

export function HandoffCard({ summary, action, actionDetail, recipeContent, onDismiss }: HandoffCardProps) {
  return (
    <div className="bg-[var(--color-bg-elevated)] border-l-4 border-[var(--color-accent)] rounded-[var(--radius-md)] shadow-sm p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 flex-1">
          <span className="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-[var(--color-accent-muted)] text-[var(--color-accent)]">
            {ACTION_LABELS[action] || 'Session ended'}
          </span>
          <p className="text-sm text-[var(--color-text-primary)] whitespace-pre-wrap">
            {summary}
          </p>
          {recipeContent && (
            <details className="mt-2">
              <summary className="text-xs font-medium text-[var(--color-accent)] cursor-pointer">
                Recipe details
              </summary>
              <pre className="mt-1.5 text-xs text-[var(--color-text-primary)] whitespace-pre-wrap bg-[var(--color-bg-secondary)] rounded-[var(--radius-sm)] p-3">
                {recipeContent}
              </pre>
            </details>
          )}
          {actionDetail && (
            <p className="text-xs text-[var(--color-text-muted)]">
              {actionDetail}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors text-lg leading-none flex-shrink-0"
        >
          &times;
        </button>
      </div>
    </div>
  )
}
