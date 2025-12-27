import { useState, FormEvent } from 'react'
import { useAuth } from '../../hooks/useAuth'

interface LoginPageProps {
  onLogin: () => void
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(email, password)
      onLogin()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)] p-4">
      <div className="w-full max-w-sm bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-xl)] p-8 shadow-lg">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-light tracking-[4px] text-[var(--color-accent)]">
            ALFRED
          </h1>
          <p className="text-[var(--color-text-muted)] mt-2 text-sm">
            Your Kitchen Assistant
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-[var(--color-text-secondary)] mb-2">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="alice@test.local"
              required
              className="w-full px-4 py-3 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent)] focus:outline-none transition-colors"
            />
          </div>

          <div>
            <label className="block text-sm text-[var(--color-text-secondary)] mb-2">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              required
              className="w-full px-4 py-3 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent)] focus:outline-none transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-semibold rounded-[var(--radius-md)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        {/* Test accounts */}
        <div className="mt-6 pt-6 border-t border-[var(--color-border)] text-sm text-[var(--color-text-muted)]">
          <strong className="text-[var(--color-text-secondary)]">Test accounts:</strong>
          <br />
          alice@test.local
          <br />
          bob@test.local
          <br />
          carol@test.local
          <br />
          <span className="text-[var(--color-accent)]">Password: alfred123</span>
        </div>
      </div>
    </div>
  )
}

