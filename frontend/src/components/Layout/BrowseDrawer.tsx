import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'

interface BrowseDrawerProps {
  isOpen: boolean
  onClose: () => void
}

const browseItems = [
  { path: '/recipes', label: 'Recipes', description: 'Your saved recipes' },
  { path: '/inventory', label: 'Inventory', description: 'Pantry & fridge items' },
  { path: '/shopping', label: 'Shopping List', description: 'Items to buy' },
  { path: '/meals', label: 'Meal Plans', description: 'Weekly meal schedule' },
  { path: '/tasks', label: 'Tasks', description: 'Reminders & to-dos' },
  { path: '/ingredients', label: 'Ingredients DB', description: 'Ingredient database' },
  { path: '/capabilities', label: 'Capabilities', description: 'What Alfred can do' },
]

export function BrowseDrawer({ isOpen, onClose }: BrowseDrawerProps) {
  const navigate = useNavigate()

  const handleNavigate = (path: string) => {
    navigate(path)
    onClose()
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/40 z-[var(--z-overlay)] md:hidden"
          />

          {/* Drawer */}
          <motion.div
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="fixed bottom-0 left-0 right-0 bg-[var(--color-bg-elevated)] rounded-t-[var(--radius-2xl)] z-[var(--z-modal)] md:hidden max-h-[80vh] overflow-hidden"
          >
            {/* Drag handle */}
            <div className="flex justify-center pt-3 pb-2">
              <div className="w-10 h-1 bg-[var(--color-border)] rounded-full" />
            </div>

            {/* Header */}
            <div className="px-5 pb-3">
              <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                Browse
              </h2>
            </div>

            {/* Items */}
            <div className="px-3 pb-6 space-y-1 overflow-y-auto">
              {browseItems.map((item) => (
                <button
                  key={item.path}
                  onClick={() => handleNavigate(item.path)}
                  className="w-full flex items-center justify-between px-4 py-3.5 rounded-[var(--radius-lg)] hover:bg-[var(--color-bg-secondary)] active:bg-[var(--color-bg-tertiary)] transition-colors text-left"
                >
                  <div>
                    <div className="text-[var(--color-text-primary)] font-semibold">
                      {item.label}
                    </div>
                    <div className="text-sm text-[var(--color-text-muted)]">
                      {item.description}
                    </div>
                  </div>
                  <span className="text-[var(--color-text-muted)] text-sm">→</span>
                </button>
              ))}
            </div>

            {/* Safe area padding for bottom */}
            <div className="h-safe-area-bottom" />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
