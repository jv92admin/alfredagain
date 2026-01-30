import { Link } from 'react-router-dom'

export function PublicHeader() {
  return (
    <header className="flex items-center justify-between px-6 py-3 bg-[var(--color-bg-elevated)] border-b border-[var(--color-border)]">
      <Link to="/about" className="text-xl font-semibold text-[var(--color-accent)]">
        Alfred
      </Link>
      <Link
        to="/"
        className="text-sm font-medium px-4 py-1.5 rounded-[var(--radius-md)] bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors"
      >
        Log In
      </Link>
    </header>
  )
}
