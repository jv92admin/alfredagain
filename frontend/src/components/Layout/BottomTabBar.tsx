import { NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'

interface BottomTabBarProps {
  onBrowseClick: () => void
}

export function BottomTabBar({ onBrowseClick }: BottomTabBarProps) {
  const location = useLocation()

  // Check if we're on the chat page
  const isChatActive = location.pathname === '/'

  // Check if we're on any browse page (entity views)
  const browsePages = ['/inventory', '/recipes', '/meals', '/shopping', '/tasks', '/ingredients']
  const isBrowseActive = browsePages.some(path => location.pathname.startsWith(path))

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[var(--color-bg-elevated)] border-t border-[var(--color-border)] z-[var(--z-sticky)] safe-area-bottom">
      <div className="flex items-center justify-around h-12">
        {/* Chat Tab */}
        <NavLink
          to="/"
          className="flex items-center justify-center flex-1 h-full relative"
        >
          {isChatActive && (
            <motion.div
              layoutId="tab-indicator"
              className="absolute top-0 left-1/2 -translate-x-1/2 w-12 h-0.5 bg-[var(--color-accent)] rounded-full"
            />
          )}
          <span className={`text-sm ${
            isChatActive
              ? 'text-[var(--color-accent)] font-semibold'
              : 'text-[var(--color-text-muted)] font-medium'
          }`}>
            Chat
          </span>
        </NavLink>

        {/* Browse Tab */}
        <button
          onClick={onBrowseClick}
          className="flex items-center justify-center flex-1 h-full relative"
        >
          {isBrowseActive && (
            <motion.div
              layoutId="tab-indicator"
              className="absolute top-0 left-1/2 -translate-x-1/2 w-12 h-0.5 bg-[var(--color-accent)] rounded-full"
            />
          )}
          <span className={`text-sm ${
            isBrowseActive
              ? 'text-[var(--color-accent)] font-semibold'
              : 'text-[var(--color-text-muted)] font-medium'
          }`}>
            Browse
          </span>
        </button>
      </div>
    </nav>
  )
}
