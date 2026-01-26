import { useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'

export function ChatFAB() {
  const navigate = useNavigate()
  const location = useLocation()

  // Only show FAB when NOT on chat page
  const showFAB = location.pathname !== '/'

  return (
    <AnimatePresence>
      {showFAB && (
        <motion.button
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0, opacity: 0 }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', damping: 20, stiffness: 300 }}
          onClick={() => navigate('/')}
          className="md:hidden fixed right-4 bottom-16 px-4 py-2.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] rounded-full shadow-lg flex items-center justify-center z-[var(--z-sticky)] font-semibold text-sm"
          aria-label="Open chat"
        >
          Chat
        </motion.button>
      )}
    </AnimatePresence>
  )
}
