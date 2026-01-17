import { useState, useCallback, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import type { User, Session } from '@supabase/supabase-js'

export interface AuthUser {
  user_id: string
  email: string
  display_name: string
}

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  // Convert Supabase user to our AuthUser format
  const toAuthUser = (supaUser: User): AuthUser => ({
    user_id: supaUser.id,
    email: supaUser.email || '',
    display_name: supaUser.user_metadata?.full_name || 
                  supaUser.user_metadata?.name || 
                  supaUser.email?.split('@')[0] || 
                  'User',
  })

  // Check current auth state
  const checkAuth = useCallback(async () => {
    try {
      const { data: { session: currentSession } } = await supabase.auth.getSession()
      
      if (currentSession?.user) {
        setSession(currentSession)
        setUser(toAuthUser(currentSession.user))
      } else {
        setSession(null)
        setUser(null)
      }
    } catch (error) {
      console.error('Auth check failed:', error)
      setSession(null)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  // Sign in with Google OAuth
  const signInWithGoogle = useCallback(async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin,
      },
    })
    
    if (error) {
      throw error
    }
  }, [])

  // Sign out
  const logout = useCallback(async () => {
    await supabase.auth.signOut()
    setSession(null)
    setUser(null)
  }, [])

  // Get access token for API calls
  const getAccessToken = useCallback((): string | null => {
    return session?.access_token || null
  }, [session])

  // Listen for auth state changes
  useEffect(() => {
    // Check initial auth state
    checkAuth()

    // Subscribe to auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, newSession) => {
        console.log('Auth state changed:', event)
        
        if (newSession?.user) {
          setSession(newSession)
          setUser(toAuthUser(newSession.user))
        } else {
          setSession(null)
          setUser(null)
        }
        setLoading(false)
      }
    )

    return () => {
      subscription.unsubscribe()
    }
  }, [checkAuth])

  return { 
    user, 
    session,
    loading, 
    checkAuth, 
    signInWithGoogle, 
    logout,
    getAccessToken,
  }
}

// Export a typed alias for backwards compatibility
export type { AuthUser as User }