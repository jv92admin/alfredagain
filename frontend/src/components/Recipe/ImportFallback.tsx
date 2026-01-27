import { motion } from 'framer-motion'

interface ImportFallbackProps {
  error: string | null
  fallbackMessage: string | null
  onTryAgain: () => void
  onClose: () => void
}

export function ImportFallback({ error, fallbackMessage, onTryAgain, onClose }: ImportFallbackProps) {
  return (
    <div className="p-6 space-y-6">
      {/* Warning icon */}
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-[var(--color-warning)]/10 mb-4">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-[var(--color-warning)]" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">
          Couldn't read this recipe automatically
        </h3>
        {error && (
          <p className="text-sm text-[var(--color-text-muted)] mb-4">
            {error}
          </p>
        )}
      </div>

      {/* Fallback message */}
      <div className="p-4 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)]">
        <p className="text-[var(--color-text-secondary)]">
          {fallbackMessage || "This site's format isn't supported yet, but no worries!"}
        </p>
        <p className="text-[var(--color-text-secondary)] mt-2">
          Copy the recipe text from the website and paste it in chat. Alfred can help you turn it into a saved recipe.
        </p>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-3">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onClose}
          className="w-full px-4 py-3 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)] flex items-center justify-center gap-2"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clipRule="evenodd" />
          </svg>
          Open Chat with Recipe Help
        </motion.button>

        <button
          onClick={onTryAgain}
          className="w-full px-4 py-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] rounded-[var(--radius-md)]"
        >
          Try Another URL
        </button>
      </div>
    </div>
  )
}
