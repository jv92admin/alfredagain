import { ReactNode, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth, User } from '../../hooks/useAuth'
import { BottomTabBar } from './BottomTabBar'
import { BrowseDrawer } from './BrowseDrawer'
import { ChatFAB } from './ChatFAB'

interface AppShellProps {
  children: ReactNode
  user: User
  onNewChat?: () => void
}

const navItems = [
  { path: '/', label: 'Chat' },
  { path: '/inventory', label: 'Inventory' },
  { path: '/recipes', label: 'Recipes' },
  { path: '/meals', label: 'Meal Plans' },
  { path: '/shopping', label: 'Shopping' },
  { path: '/tasks', label: 'Tasks' },
  { path: '/ingredients', label: 'Ingredients DB' },
  { path: '/preferences', label: 'Preferences' },
]

export function AppShell({ children, user, onNewChat }: AppShellProps) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [browseDrawerOpen, setBrowseDrawerOpen] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="h-dvh bg-[var(--color-bg-primary)] flex overflow-hidden">
      {/* Desktop Sidebar - Fixed */}
      <aside className="hidden md:flex flex-col w-[var(--sidebar-width)] bg-[var(--color-bg-secondary)] border-r border-[var(--color-border)] flex-shrink-0">
        {/* Logo */}
        <div className="p-4 border-b border-[var(--color-border)]">
          <h1 className="text-xl font-semibold text-[var(--color-accent)]">
            Alfred
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
                `block px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-[var(--color-accent-muted)] text-[var(--color-accent)] font-semibold border-r-2 border-[var(--color-accent)]'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)]'
                }`
              }
            >
              {item.label}
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
        {/* Mobile Header */}
        <header className="md:hidden flex items-center justify-between px-4 py-3 bg-[var(--color-bg-elevated)] border-b border-[var(--color-border)] flex-shrink-0">
          <h1 className="text-lg font-semibold text-[var(--color-accent)]">
            Alfred
          </h1>
          <div className="flex items-center gap-4">
            {onNewChat && (
              <button
                onClick={onNewChat}
                className="text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-colors"
              >
                + New
              </button>
            )}
            <NavLink
              to="/preferences"
              className={({ isActive }) =>
                `text-sm font-medium transition-colors ${
                  isActive
                    ? 'text-[var(--color-accent)]'
                    : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'
                }`
              }
            >
              Settings
            </NavLink>
          </div>
        </header>

        {/* Page Content - Scrollable with bottom padding on mobile for tab bar */}
        <main className="flex-1 overflow-auto pb-12 md:pb-0">
          {children}
        </main>
      </div>

      {/* Mobile Navigation */}
      <BottomTabBar onBrowseClick={() => setBrowseDrawerOpen(true)} />
      <BrowseDrawer
        isOpen={browseDrawerOpen}
        onClose={() => setBrowseDrawerOpen(false)}
      />
      <ChatFAB />
    </div>
  )
}
