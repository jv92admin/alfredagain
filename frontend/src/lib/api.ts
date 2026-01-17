/**
 * API client utilities for making authenticated requests to the backend.
 */

import { supabase } from './supabase'

/**
 * Get the current access token for API authentication.
 */
async function getAccessToken(): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession()
  return session?.access_token || null
}

/**
 * Make an authenticated API request.
 * Automatically includes the Authorization header with the JWT token.
 */
export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getAccessToken()
  
  if (!token) {
    throw new Error('Not authenticated')
  }

  const response = await fetch(endpoint, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/**
 * Make a streaming API request (for SSE).
 * Returns the Response object so the caller can handle streaming.
 */
export async function apiStream(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = await getAccessToken()
  
  if (!token) {
    throw new Error('Not authenticated')
  }

  const response = await fetch(endpoint, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response
}
