import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { RecipePreviewForm } from './RecipePreviewForm'
import { ImportFallback } from './ImportFallback'

interface RecipePreview {
  name: string
  source_url: string
  description: string | null
  prep_time_minutes: number | null
  cook_time_minutes: number | null
  servings: number | null
  cuisine: string | null
  ingredients_raw: string[]
  instructions: string[]
  image_url: string | null
}

interface ImportResponse {
  success: boolean
  method: string
  preview: RecipePreview | null
  error: string | null
  fallback_message: string | null
}

interface RecipeImportModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

type ImportState = 'input' | 'loading' | 'preview' | 'fallback' | 'saving'

export function RecipeImportModal({ isOpen, onClose, onSuccess }: RecipeImportModalProps) {
  const [url, setUrl] = useState('')
  const [state, setState] = useState<ImportState>('input')
  const [preview, setPreview] = useState<RecipePreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fallbackMessage, setFallbackMessage] = useState<string | null>(null)

  const resetState = () => {
    setUrl('')
    setState('input')
    setPreview(null)
    setError(null)
    setFallbackMessage(null)
  }

  const handleClose = () => {
    resetState()
    onClose()
  }

  const handleImport = async () => {
    if (!url.trim()) {
      setError('Please enter a URL')
      return
    }

    // Basic URL validation
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setError('URL must start with http:// or https://')
      return
    }

    setError(null)
    setState('loading')

    try {
      const response: ImportResponse = await apiRequest('/api/recipes/import', {
        method: 'POST',
        body: JSON.stringify({ url: url.trim() }),
      })

      if (response.success && response.preview) {
        setPreview(response.preview)
        setState('preview')
      } else {
        setError(response.error || 'Failed to extract recipe')
        setFallbackMessage(response.fallback_message || null)
        setState('fallback')
      }
    } catch (err) {
      console.error('Import error:', err)
      setError('Failed to import recipe. Please try again.')
      setState('fallback')
    }
  }

  const handleSaveSuccess = () => {
    onSuccess()
    handleClose()
  }

  const handleTryAgain = () => {
    setUrl('')
    setState('input')
    setError(null)
    setFallbackMessage(null)
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          onClick={handleClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-[var(--color-bg-primary)] rounded-[var(--radius-lg)] shadow-xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
              <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">
                {state === 'preview' ? 'Review Imported Recipe' : 'Import Recipe from URL'}
              </h2>
              <button
                onClick={handleClose}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto">
              {/* URL Input State */}
              {state === 'input' && (
                <div className="p-6 space-y-6">
                  <div className="text-center">
                    <div className="text-4xl mb-4">📎</div>
                    <p className="text-[var(--color-text-secondary)]">
                      Paste a recipe link from AllRecipes, Food Network, Serious Eats, and 400+ more sites
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                      Recipe URL
                    </label>
                    <input
                      type="url"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleImport()}
                      placeholder="https://www.allrecipes.com/recipe/..."
                      autoFocus
                      className="w-full px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
                    />
                    {error && (
                      <p className="mt-2 text-sm text-[var(--color-error)]">{error}</p>
                    )}
                  </div>

                  <div className="flex justify-end gap-3">
                    <button
                      onClick={handleClose}
                      className="px-4 py-2 rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]"
                    >
                      Cancel
                    </button>
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={handleImport}
                      className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)]"
                    >
                      Import
                    </motion.button>
                  </div>
                </div>
              )}

              {/* Loading State */}
              {state === 'loading' && (
                <div className="p-12 text-center">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-[var(--color-accent)] border-r-transparent mb-4"></div>
                  <p className="text-[var(--color-text-secondary)]">
                    Extracting recipe from {new URL(url).hostname}...
                  </p>
                </div>
              )}

              {/* Preview State */}
              {state === 'preview' && preview && (
                <RecipePreviewForm
                  preview={preview}
                  onSave={handleSaveSuccess}
                  onCancel={handleClose}
                  onSaving={() => setState('saving')}
                  onSaveError={() => setState('preview')}
                />
              )}

              {/* Saving State */}
              {state === 'saving' && (
                <div className="p-12 text-center">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-[var(--color-accent)] border-r-transparent mb-4"></div>
                  <p className="text-[var(--color-text-secondary)]">
                    Saving recipe...
                  </p>
                </div>
              )}

              {/* Fallback State */}
              {state === 'fallback' && (
                <ImportFallback
                  error={error}
                  fallbackMessage={fallbackMessage}
                  onTryAgain={handleTryAgain}
                  onClose={handleClose}
                />
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
