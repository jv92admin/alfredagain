import { useState } from 'react'
import { useAuth } from '../../hooks/useAuth'

interface LoginPageProps {
  onLogin?: () => void  // Optional - auth state change handles this automatically
}

export function LoginPage({ onLogin: _onLogin }: LoginPageProps) {
  const { signInWithGoogle } = useAuth()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleGoogleSignIn = async () => {
    setError('')
    setLoading(true)

    try {
      await signInWithGoogle()
      // Note: onLogin will be called automatically when auth state changes
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-dvh flex items-center justify-center bg-[var(--color-bg-primary)] p-4">
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

        {/* Google Sign In Button */}
        <button
          onClick={handleGoogleSignIn}
          disabled={loading}
          className="w-full py-3 bg-white hover:bg-gray-50 text-gray-900 font-semibold rounded-[var(--radius-md)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-gray-300 flex items-center justify-center gap-3"
        >
          {loading ? (
            'Signing in...'
          ) : (
            <>
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              Sign in with Google
            </>
          )}
        </button>

        {/* Info */}
        <div className="mt-6 pt-6 border-t border-[var(--color-border)] text-sm text-[var(--color-text-muted)] text-center">
          Sign in with your Google account to get started.
        </div>
      </div>
    </div>
  )
}

