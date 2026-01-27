import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { SessionStatusResponse } from '../../types/session'

interface ResumePromptProps {
  sessionStatus: SessionStatusResponse
  onResume: () => void
  onStartFresh: () => void
}

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`
  return date.toLocaleDateString()
}

export function ResumePrompt({ sessionStatus, onResume, onStartFresh }: ResumePromptProps) {
  // Handle escape key - implicit resume
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onResume()
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [onResume])

  const { preview, last_active_at } = sessionStatus

  return (
    <div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center p-4">
      {/* Backdrop - click = implicit resume */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onResume}
        className="absolute inset-0 bg-black/60"
      />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="relative bg-[var(--color-bg-secondary)] rounded-[var(--radius-lg)] shadow-xl max-w-sm w-full overflow-hidden"
      >
        {/* Content */}
        <div className="p-6">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2">
            Welcome back!
          </h2>
          <p className="text-[var(--color-text-secondary)] text-sm mb-4">
            You have an ongoing conversation.
          </p>

          {/* Preview */}
          {preview && (
            <div className="bg-[var(--color-bg-primary)] rounded-[var(--radius-md)] p-3 mb-4 border border-[var(--color-border)]">
              <p className="text-[var(--color-text-primary)] text-sm mb-1">
                {preview.last_message}
              </p>
              <p className="text-[var(--color-text-muted)] text-xs">
                {preview.message_count} message{preview.message_count === 1 ? '' : 's'}
                {last_active_at && ` · ${formatRelativeTime(last_active_at)}`}
              </p>
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-3">
            <button
              onClick={onStartFresh}
              className="flex-1 px-4 py-2.5 text-sm font-medium text-[var(--color-text-secondary)] bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
            >
              Start Fresh
            </button>
            <button
              onClick={onResume}
              className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-[var(--color-accent)] rounded-[var(--radius-md)] hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              Resume
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
