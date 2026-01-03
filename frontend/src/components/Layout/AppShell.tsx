import { ReactNode, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth, User } from '../../hooks/useAuth'

interface AppShellProps {
  children: ReactNode
  user: User
  onNewChat?: () => void
}

const navItems = [
  { path: '/', label: 'Chat', icon: '💬' },
  { path: '/inventory', label: 'Inventory', icon: '📦' },
  { path: '/recipes', label: 'Recipes', icon: '🍳' },
  { path: '/meals', label: 'Meal Plans', icon: '📅' },
  { path: '/shopping', label: 'Shopping', icon: '🛒' },
  { path: '/tasks', label: 'Tasks', icon: '✅' },
  { path: '/ingredients', label: 'Ingredients DB', icon: '🧂' },
]

export function AppShell({ children, user, onNewChat }: AppShellProps) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="h-screen bg-[var(--color-bg-primary)] flex overflow-hidden">
      {/* Desktop Sidebar - Fixed */}
      <aside className="hidden md:flex flex-col w-[var(--sidebar-width)] bg-[var(--color-bg-secondary)] border-r border-[var(--color-border)] flex-shrink-0">
        {/* Logo */}
        <div className="p-4 border-b border-[var(--color-border)]">
          <h1 className="text-xl font-light tracking-[3px] text-[var(--color-accent)]">
            ALFRED
          </h1>
        </div>

        {/* New Chat Button */}
        {onNewChat && (
          <div className="px-4 py-3">
            <button
              onClick={onNewChat}
              className="w-full flex items-center justify-center gap-2 py-2 bg-[var(--color-bg-tertiary)] hover:bg-[var(--color-accent-muted)] border border-[var(--color-border)] hover:border-[var(--color-accent)] rounded-[var(--radius-md)] text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] transition-colors"
            >
              <span>+</span>
              <span>New Chat</span>
            </button>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                  isActive
                    ? 'bg-[var(--color-accent-muted)] text-[var(--color-accent)] border-r-2 border-[var(--color-accent)]'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)]'
                }`
              }
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="p-4 border-t border-[var(--color-border)]">
          <div className="text-sm text-[var(--color-text-secondary)] mb-2">
            {user.display_name}
          </div>
          <button
            onClick={handleLogout}
            className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors"
          >
            Logout
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Mobile Header - Sticky */}
        <header className="md:hidden flex items-center justify-between p-4 bg-[var(--color-bg-secondary)] border-b border-[var(--color-border)] flex-shrink-0">
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="text-2xl text-[var(--color-text-primary)]"
          >
            ☰
          </button>
          <h1 className="text-lg font-light tracking-[2px] text-[var(--color-accent)]">
            ALFRED
          </h1>
        </header>

        {/* Page Content - Scrollable */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>

      {/* Mobile Drawer */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileMenuOpen(false)}
              className="fixed inset-0 bg-black/50 z-[var(--z-overlay)] md:hidden"
            />

            {/* Drawer */}
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="fixed top-0 left-0 bottom-0 w-64 bg-[var(--color-bg-secondary)] border-r border-[var(--color-border)] z-[var(--z-modal)] md:hidden"
            >
              {/* Close button */}
              <div className="p-4 border-b border-[var(--color-border)] flex justify-between items-center">
                <span className="text-[var(--color-text-secondary)]">Menu</span>
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="text-xl text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                >
                  ✕
                </button>
              </div>

              {/* New Chat Button */}
              {onNewChat && (
                <div className="px-4 py-3 border-b border-[var(--color-border)]">
                  <button
                    onClick={() => {
                      onNewChat()
                      setMobileMenuOpen(false)
                    }}
                    className="w-full flex items-center justify-center gap-2 py-2 bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded-[var(--radius-md)] text-sm font-medium"
                  >
                    <span>+</span>
                    <span>New Chat</span>
                  </button>
                </div>
              )}

              {/* Navigation */}
              <nav className="py-4">
                {navItems.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    onClick={() => setMobileMenuOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                        isActive
                          ? 'bg-[var(--color-accent-muted)] text-[var(--color-accent)]'
                          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]'
                      }`
                    }
                  >
                    <span>{item.icon}</span>
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </nav>

              {/* User */}
              <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-[var(--color-border)]">
                <div className="text-sm text-[var(--color-text-secondary)] mb-2">
                  {user.display_name}
                </div>
                <button
                  onClick={handleLogout}
                  className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors"
                >
                  Logout
                </button>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}
