/**
 * Hook for fetching and caching schema data from the backend.
 * Provides type information, enums, and JSON Schema for forms.
 */

import { useState, useEffect, useCallback } from 'react'
import { apiRequest } from '../lib/api'

// =============================================================================
// Types
// =============================================================================

export interface SubdomainOverview {
  tables: string[]
  primary: string | null
}

export interface SubdomainSchema {
  subdomain: string
  tables: string[]
  enums: Record<string, string[]>
}

export interface FormSchema {
  create: JSONSchema | null
  update: JSONSchema | null
  enums: Record<string, string[]>
}

export interface JSONSchema {
  type?: string
  title?: string
  properties?: Record<string, JSONSchemaProperty>
  required?: string[]
  $defs?: Record<string, JSONSchema>
}

export interface JSONSchemaProperty {
  type?: string | string[]
  title?: string
  description?: string
  enum?: string[]
  format?: string
  default?: any
  items?: JSONSchemaProperty
  $ref?: string
  anyOf?: JSONSchemaProperty[]
  allOf?: JSONSchemaProperty[]
  // Number constraints
  minimum?: number
  maximum?: number
  multipleOf?: number
  exclusiveMinimum?: number
  exclusiveMaximum?: number
}

// =============================================================================
// Schema Cache
// =============================================================================

const schemaCache: {
  subdomains: Record<string, SubdomainOverview> | null
  schemas: Map<string, SubdomainSchema>
  forms: Map<string, FormSchema>
} = {
  subdomains: null,
  schemas: new Map(),
  forms: new Map(),
}

// =============================================================================
// Hook: useSchemaOverview
// =============================================================================

export function useSchemaOverview() {
  const [subdomains, setSubdomains] = useState<Record<string, SubdomainOverview> | null>(
    schemaCache.subdomains
  )
  const [loading, setLoading] = useState(!schemaCache.subdomains)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (schemaCache.subdomains) {
      setSubdomains(schemaCache.subdomains)
      return
    }

    const fetchOverview = async () => {
      try {
        const data = await apiRequest<{ subdomains: Record<string, SubdomainOverview> }>(
          '/api/schema'
        )
        schemaCache.subdomains = data.subdomains
        setSubdomains(data.subdomains)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load schemas')
      } finally {
        setLoading(false)
      }
    }

    fetchOverview()
  }, [])

  return { subdomains, loading, error }
}

// =============================================================================
// Hook: useSubdomainSchema
// =============================================================================

export function useSubdomainSchema(subdomain: string) {
  const [schema, setSchema] = useState<SubdomainSchema | null>(
    schemaCache.schemas.get(subdomain) || null
  )
  const [loading, setLoading] = useState(!schemaCache.schemas.has(subdomain))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (schemaCache.schemas.has(subdomain)) {
      setSchema(schemaCache.schemas.get(subdomain)!)
      setLoading(false)
      return
    }

    const fetchSchema = async () => {
      try {
        const data = await apiRequest<SubdomainSchema>(`/api/schema/${subdomain}`)
        schemaCache.schemas.set(subdomain, data)
        setSchema(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load schema')
      } finally {
        setLoading(false)
      }
    }

    fetchSchema()
  }, [subdomain])

  return { schema, loading, error }
}

// =============================================================================
// Hook: useFormSchema
// =============================================================================

export function useFormSchema(subdomain: string) {
  const [formSchema, setFormSchema] = useState<FormSchema | null>(
    schemaCache.forms.get(subdomain) || null
  )
  const [loading, setLoading] = useState(!schemaCache.forms.has(subdomain))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (schemaCache.forms.has(subdomain)) {
      setFormSchema(schemaCache.forms.get(subdomain)!)
      setLoading(false)
      return
    }

    const fetchFormSchema = async () => {
      try {
        const data = await apiRequest<FormSchema>(`/api/schema/${subdomain}/form`)
        schemaCache.forms.set(subdomain, data)
        setFormSchema(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load form schema')
      } finally {
        setLoading(false)
      }
    }

    fetchFormSchema()
  }, [subdomain])

  // Helper to get enum values for a field
  const getEnumValues = useCallback(
    (fieldName: string): string[] | undefined => {
      return formSchema?.enums[fieldName]
    },
    [formSchema]
  )

  // Helper to check if a field is required
  const isRequired = useCallback(
    (fieldName: string): boolean => {
      return formSchema?.create?.required?.includes(fieldName) ?? false
    },
    [formSchema]
  )

  return { formSchema, loading, error, getEnumValues, isRequired }
}

// =============================================================================
// Cache Invalidation
// =============================================================================

export function invalidateSchemaCache(subdomain?: string) {
  if (subdomain) {
    schemaCache.schemas.delete(subdomain)
    schemaCache.forms.delete(subdomain)
  } else {
    schemaCache.subdomains = null
    schemaCache.schemas.clear()
    schemaCache.forms.clear()
  }
}
