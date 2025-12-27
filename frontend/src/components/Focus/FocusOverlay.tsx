import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { RecipeDetail } from './RecipeDetail'
import { MealPlanDetail } from './MealPlanDetail'

interface FocusOverlayProps {
  type: string
  id: string
  onClose: () => void
}

export function FocusOverlay({ type, id, onClose }: FocusOverlayProps) {
  // Prevent body scroll when overlay is open
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[var(--z-modal)]">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/70"
      />

      {/* Content */}
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="absolute inset-0 md:inset-4 md:top-8 bg-[var(--color-bg-primary)] md:rounded-t-[var(--radius-xl)] overflow-hidden flex flex-col"
      >
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
          <button
            onClick={onClose}
            className="flex items-center gap-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <span>←</span>
            <span>Back</span>
          </button>
          <div className="w-16" /> {/* Spacer for layout balance */}
        </header>

        {/* Detail content */}
        <div className="flex-1 overflow-y-auto">
          {type === 'recipe' && <RecipeDetail id={id} onClose={onClose} />}
          {type === 'meal_plan' && <MealPlanDetail id={id} />}
        </div>

        {/* Sticky input */}
        <div className="border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
          <input
            type="text"
            placeholder={`Ask about this ${type.replace('_', ' ')}...`}
            className="w-full px-4 py-3 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent)] focus:outline-none"
          />
        </div>
      </motion.div>
    </div>
  )
}

