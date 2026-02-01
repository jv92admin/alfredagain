/**
 * EntityForm - Generic schema-driven form for creating/editing entities.
 *
 * Uses JSON Schema from the backend to render form fields automatically.
 * Supports custom renderers for complex fields like ingredients lists.
 */

import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useFormSchema } from '../../hooks/useSchema'
import { FieldRenderer, type FieldRendererProps } from './FieldRenderer'
import { apiRequest } from '../../lib/api'

// =============================================================================
// Types
// =============================================================================

export interface EntityFormProps {
  subdomain: string
  table: string
  mode: 'create' | 'edit'
  entityId?: string
  initialData?: Record<string, any>
  onSuccess: (data: any, meta: any) => void
  onCancel: () => void
  customRenderers?: Record<string, React.ComponentType<FieldRendererProps>>
  excludeFields?: string[]
  fieldOrder?: string[]
}

interface EntityResponse {
  data: Record<string, any>
  meta: {
    action: string
    entity_type: string
    id: string
    timestamp: string
  }
}

// =============================================================================
// Component
// =============================================================================

export function EntityForm({
  subdomain,
  table,
  mode,
  entityId,
  initialData,
  onSuccess,
  onCancel,
  customRenderers,
  excludeFields = ['id', 'user_id', 'created_at', 'updated_at'],
  fieldOrder,
}: EntityFormProps) {
  const { formSchema, loading: schemaLoading, error: schemaError, isRequired } = useFormSchema(subdomain)
  const [formData, setFormData] = useState<Record<string, any>>(initialData || {})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Initialize form data when initialData or schema changes
  useEffect(() => {
    if (initialData) {
      setFormData(initialData)
    } else if (formSchema?.create?.properties) {
      // Set defaults from schema
      const defaults: Record<string, any> = {}
      for (const [key, prop] of Object.entries(formSchema.create.properties)) {
        if (prop.default !== undefined) {
          defaults[key] = prop.default
        }
      }
      setFormData(defaults)
    }
  }, [initialData, formSchema])

  // Get ordered list of fields to render
  const fields = useMemo(() => {
    if (!formSchema?.create?.properties) return []

    const allFields = Object.keys(formSchema.create.properties)
      .filter((name) => !excludeFields.includes(name))

    if (fieldOrder) {
      // Use specified order, then append any remaining fields
      const ordered = fieldOrder.filter((f) => allFields.includes(f))
      const remaining = allFields.filter((f) => !fieldOrder.includes(f))
      return [...ordered, ...remaining]
    }

    return allFields
  }, [formSchema, excludeFields, fieldOrder])

  // Update a single field
  const updateField = (name: string, value: any) => {
    setFormData((prev) => ({ ...prev, [name]: value }))
    // Clear error when field is updated
    if (errors[name]) {
      setErrors((prev) => {
        const next = { ...prev }
        delete next[name]
        return next
      })
    }
  }

  // Validate form before submit
  const validate = (): boolean => {
    const newErrors: Record<string, string> = {}

    for (const field of fields) {
      if (isRequired(field)) {
        const value = formData[field]
        if (value === undefined || value === null || value === '') {
          newErrors[field] = 'This field is required'
        }
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  // Submit form
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!validate()) return

    setSubmitting(true)
    setSubmitError(null)

    try {
      const endpoint = mode === 'create'
        ? `/api/entities/${table}`
        : `/api/entities/${table}/${entityId}`

      const response = await apiRequest<EntityResponse>(endpoint, {
        method: mode === 'create' ? 'POST' : 'PATCH',
        body: JSON.stringify(formData),
      })

      onSuccess(response.data, response.meta)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSubmitting(false)
    }
  }

  // Loading state
  if (schemaLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[var(--color-text-secondary)]">Loading form...</div>
      </div>
    )
  }

  // Error state
  if (schemaError) {
    return (
      <div className="p-4 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)]">
        Failed to load form: {schemaError}
      </div>
    )
  }

  // No schema
  if (!formSchema?.create?.properties) {
    return (
      <div className="p-4 bg-[var(--color-warning-muted)] border border-[var(--color-warning)] rounded-[var(--radius-md)] text-[var(--color-warning)]">
        No form schema available for {subdomain}
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Error banner */}
      {submitError && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm"
        >
          {submitError}
        </motion.div>
      )}

      {/* Form fields */}
      <div className="space-y-4">
        {fields.map((fieldName) => {
          const schema = formSchema.create!.properties![fieldName]
          const CustomRenderer = customRenderers?.[fieldName]

          return (
            <FieldRenderer
              key={fieldName}
              name={fieldName}
              schema={schema}
              value={formData[fieldName]}
              onChange={(value) => updateField(fieldName, value)}
              enums={formSchema.enums}
              required={isRequired(fieldName)}
              error={errors[fieldName]}
              disabled={submitting}
              customRenderer={CustomRenderer}
              updateFormData={(updates) => {
                setFormData((prev) => ({ ...prev, ...updates }))
              }}
            />
          )
        })}
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-[var(--color-border)]">
        <motion.button
          type="button"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onCancel}
          disabled={submitting}
          className="px-4 py-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] disabled:opacity-50"
        >
          Cancel
        </motion.button>
        <motion.button
          type="submit"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          disabled={submitting}
          className="px-6 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)] disabled:opacity-50"
        >
          {submitting ? 'Saving...' : mode === 'create' ? 'Create' : 'Save'}
        </motion.button>
      </div>
    </form>
  )
}

// =============================================================================
// Modal Wrapper (convenience component)
// =============================================================================

interface EntityFormModalProps extends Omit<EntityFormProps, 'onCancel'> {
  title: string
  isOpen: boolean
  onClose: () => void
}

export function EntityFormModal({
  title,
  isOpen,
  onClose,
  onSuccess,
  ...formProps
}: EntityFormModalProps) {
  if (!isOpen) return null

  const handleSuccess = (data: any, meta: any) => {
    onSuccess(data, meta)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-lg max-h-[90vh] overflow-auto bg-[var(--color-bg-primary)] rounded-[var(--radius-lg)] shadow-xl mx-4"
      >
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between px-6 py-4 bg-[var(--color-bg-primary)] border-b border-[var(--color-border)]">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">{title}</h2>
          <button
            onClick={onClose}
            className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <div className="p-6">
          <EntityForm
            {...formProps}
            onSuccess={handleSuccess}
            onCancel={onClose}
          />
        </div>
      </motion.div>
    </div>
  )
}
