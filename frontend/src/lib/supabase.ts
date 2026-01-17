import { createClient } from '@supabase/supabase-js'

// Get Supabase URL and anon key from environment variables
// These are public and safe to expose in the frontend
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  console.error('Missing Supabase environment variables. Make sure VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set.')
}

export const supabase = createClient(supabaseUrl || '', supabaseAnonKey || '')
