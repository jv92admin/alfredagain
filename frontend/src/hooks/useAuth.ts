import { useState, useCallback } from 'react'

export interface User {
  user_id: string
  email: string
  display_name: string
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    try {
      const res = await fetch('/api/me', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setUser(data)
      } else {
        setUser(null)
      }
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      credentials: 'include',
    })
    
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || 'Login failed')
    }
    
    await checkAuth()
  }, [checkAuth])

  const logout = useCallback(async () => {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
  }, [])

  return { user, loading, checkAuth, login, logout }
}

