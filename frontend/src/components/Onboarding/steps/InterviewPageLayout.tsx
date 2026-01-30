import { ReactNode } from 'react'
import { motion } from 'framer-motion'

interface InterviewPageLayoutProps {
  pageNumber: number
  totalPages: number
  title: string
  subtitle: string
  image?: string
  children: ReactNode
  onBack: () => void
  onSkip?: () => void
  onSubmit: () => void
  submitLabel?: string
  submitting?: boolean
  canGoBack?: boolean
  error?: string
}

export function InterviewPageLayout({
  pageNumber,
  totalPages,
  title,
  subtitle,
  image,
  children,
  onBack,
  onSkip,
  onSubmit,
  submitLabel = 'Continue',
  submitting = false,
  canGoBack = true,
  error,
}: InterviewPageLayoutProps) {
  return (
    <div className="space-y-6">
      {/* Progress */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide">
          Part {pageNumber} of {totalPages}
        </span>
      </div>

      {/* Hero Image */}
      {image && (
        <div className="w-full h-40 rounded-[var(--radius-lg)] overflow-hidden bg-[var(--color-bg-secondary)] border border-[var(--color-border-subtle)]">
          <img
            src={image}
            alt={title}
            className="w-full h-full object-cover"
            onError={(e) => {
              // Hide broken placeholder images gracefully
              (e.target as HTMLImageElement).style.display = 'none'
            }}
          />
        </div>
      )}

      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          {title}
        </h2>
        <p className="text-[var(--color-text-muted)]">
          {subtitle}
        </p>
      </div>

      {error && (
        <div className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
          {error}
        </div>
      )}

      {/* Question Content */}
      <div className="space-y-6">
        {children}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-[var(--color-border-subtle)]">
        <div>
          {canGoBack && (
            <button
              onClick={onBack}
              disabled={submitting}
              className="px-4 py-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors disabled:opacity-50"
            >
              ← Back
            </button>
          )}
        </div>

        <div className="flex gap-3">
          {onSkip && (
            <button
              onClick={onSkip}
              disabled={submitting}
              className="px-4 py-2 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors disabled:opacity-50 text-sm"
            >
              Skip this section
            </button>
          )}

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onSubmit}
            disabled={submitting}
            className="
              px-8 py-3
              bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)]
              text-[var(--color-text-inverse)]
              font-semibold
              rounded-[var(--radius-lg)]
              transition-colors
              disabled:opacity-50
            "
          >
            {submitting ? 'Saving...' : submitLabel}
          </motion.button>
        </div>
      </div>

      {/* Progress dots */}
      <div className="flex justify-center gap-2 pt-2">
        {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
          <div
            key={page}
            className={`
              w-2 h-2 rounded-full transition-colors
              ${page === pageNumber
                ? 'bg-[var(--color-accent)]'
                : page < pageNumber
                  ? 'bg-[var(--color-accent-muted)]'
                  : 'bg-[var(--color-border)]'
              }
            `}
          />
        ))}
      </div>
    </div>
  )
}
