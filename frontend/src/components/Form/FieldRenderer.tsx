/**
 * FieldRenderer - Maps JSON Schema property types to form widgets.
 *
 * Type mapping:
 * - string → TextInput
 * - string + enum → Select/Dropdown
 * - string + format:date → DatePicker
 * - integer/number → NumberInput
 * - boolean → Checkbox
 * - array of string → ChipsInput (multi-select)
 * - array of objects → Custom component required (renders slot)
 */

import { motion } from 'framer-motion'
import type { JSONSchemaProperty } from '../../hooks/useSchema'

// =============================================================================
// Types
// =============================================================================

export interface FieldRendererProps {
  name: string
  label?: string
  schema: JSONSchemaProperty
  value: any
  onChange: (value: any) => void
  enums?: Record<string, string[]>
  required?: boolean
  error?: string
  disabled?: boolean
  placeholder?: string
  customRenderer?: React.ComponentType<FieldRendererProps>
  /** Allows custom renderers to set sibling form fields (e.g., ingredient_id, category). */
  updateFormData?: (updates: Record<string, any>) => void
}

// =============================================================================
// Component
// =============================================================================

export function FieldRenderer({
  name,
  label,
  schema,
  value,
  onChange,
  enums,
  required,
  error,
  disabled,
  placeholder,
  customRenderer: CustomRenderer,
  updateFormData,
}: FieldRendererProps) {
  // Use custom renderer if provided
  if (CustomRenderer) {
    return (
      <CustomRenderer
        name={name}
        label={label}
        schema={schema}
        value={value}
        onChange={onChange}
        enums={enums}
        required={required}
        error={error}
        disabled={disabled}
        placeholder={placeholder}
        updateFormData={updateFormData}
      />
    )
  }

  // Resolve $ref if present (simplified - assumes local refs)
  const resolvedSchema = schema

  // Check for enum from schema or external enums
  const enumValues = resolvedSchema.enum || enums?.[name]

  // Determine field type
  const fieldType = Array.isArray(resolvedSchema.type)
    ? resolvedSchema.type.find((t) => t !== 'null') || 'string'
    : resolvedSchema.type || 'string'

  // Check for array of objects (complex type requiring custom editor)
  if (fieldType === 'array' && resolvedSchema.items?.type === 'object') {
    return (
      <FieldWrapper label={label || name} required={required} error={error}>
        <div className="p-4 rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-[var(--color-text-muted)] text-sm">
          Custom editor required for this field
        </div>
      </FieldWrapper>
    )
  }

  // Render based on type
  if (enumValues) {
    return (
      <SelectField
        name={name}
        label={label}
        value={value}
        onChange={onChange}
        options={enumValues}
        required={required}
        error={error}
        disabled={disabled}
        placeholder={placeholder}
      />
    )
  }

  if (fieldType === 'boolean') {
    return (
      <CheckboxField
        name={name}
        label={label}
        value={value}
        onChange={onChange}
        disabled={disabled}
        error={error}
      />
    )
  }

  if (fieldType === 'integer' || fieldType === 'number') {
    return (
      <NumberField
        name={name}
        label={label}
        value={value}
        onChange={onChange}
        required={required}
        error={error}
        disabled={disabled}
        placeholder={placeholder}
        schema={resolvedSchema}
      />
    )
  }

  if (resolvedSchema.format === 'date') {
    return (
      <DateField
        name={name}
        label={label}
        value={value}
        onChange={onChange}
        required={required}
        error={error}
        disabled={disabled}
      />
    )
  }

  if (fieldType === 'array') {
    // Array of strings - chips input
    return (
      <ChipsField
        name={name}
        label={label}
        value={value}
        onChange={onChange}
        required={required}
        error={error}
        disabled={disabled}
        options={enums?.[name]}
      />
    )
  }

  // Default: text input
  return (
    <TextField
      name={name}
      label={label}
      value={value}
      onChange={onChange}
      required={required}
      error={error}
      disabled={disabled}
      placeholder={placeholder}
      multiline={name === 'description' || name === 'notes'}
    />
  )
}

// =============================================================================
// Field Wrapper
// =============================================================================

interface FieldWrapperProps {
  label?: string
  required?: boolean
  error?: string
  children: React.ReactNode
}

function FieldWrapper({ label, required, error, children }: FieldWrapperProps) {
  return (
    <div className="space-y-1.5">
      {label && (
        <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
          {label}
          {required && <span className="text-[var(--color-error)] ml-1">*</span>}
        </label>
      )}
      {children}
      {error && (
        <p className="text-xs text-[var(--color-error)]">{error}</p>
      )}
    </div>
  )
}

// =============================================================================
// Text Field
// =============================================================================

interface TextFieldProps {
  name: string
  label?: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  error?: string
  disabled?: boolean
  placeholder?: string
  multiline?: boolean
}

function TextField({
  name,
  label,
  value,
  onChange,
  required,
  error,
  disabled,
  placeholder,
  multiline,
}: TextFieldProps) {
  const inputClasses = `
    w-full px-3 py-2 rounded-[var(--radius-md)]
    bg-[var(--color-bg-secondary)] border border-[var(--color-border)]
    text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]
    focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]
    disabled:opacity-50 disabled:cursor-not-allowed
    ${error ? 'border-[var(--color-error)]' : ''}
  `

  return (
    <FieldWrapper label={label || formatLabel(name)} required={required} error={error}>
      {multiline ? (
        <textarea
          name={name}
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder={placeholder}
          rows={3}
          className={inputClasses + ' resize-y'}
        />
      ) : (
        <input
          type="text"
          name={name}
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder={placeholder}
          className={inputClasses}
        />
      )}
    </FieldWrapper>
  )
}

// =============================================================================
// Number Field
// =============================================================================

interface NumberFieldProps {
  name: string
  label?: string
  value: number | null
  onChange: (value: number | null) => void
  required?: boolean
  error?: string
  disabled?: boolean
  placeholder?: string
  schema?: JSONSchemaProperty
}

function NumberField({
  name,
  label,
  value,
  onChange,
  required,
  error,
  disabled,
  placeholder,
  schema,
}: NumberFieldProps) {
  return (
    <FieldWrapper label={label || formatLabel(name)} required={required} error={error}>
      <input
        type="number"
        name={name}
        value={value ?? ''}
        onChange={(e) => {
          const val = e.target.value
          onChange(val === '' ? null : parseFloat(val))
        }}
        disabled={disabled}
        placeholder={placeholder}
        min={schema?.minimum as number | undefined}
        max={schema?.maximum as number | undefined}
        step={schema?.multipleOf as number | undefined}
        className={`
          w-full px-3 py-2 rounded-[var(--radius-md)]
          bg-[var(--color-bg-secondary)] border border-[var(--color-border)]
          text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]
          focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]
          disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? 'border-[var(--color-error)]' : ''}
        `}
      />
    </FieldWrapper>
  )
}

// =============================================================================
// Select Field
// =============================================================================

interface SelectFieldProps {
  name: string
  label?: string
  value: string
  onChange: (value: string) => void
  options: string[]
  required?: boolean
  error?: string
  disabled?: boolean
  placeholder?: string
}

function SelectField({
  name,
  label,
  value,
  onChange,
  options,
  required,
  error,
  disabled,
  placeholder,
}: SelectFieldProps) {
  return (
    <FieldWrapper label={label || formatLabel(name)} required={required} error={error}>
      <select
        name={name}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={`
          w-full px-3 py-2 rounded-[var(--radius-md)]
          bg-[var(--color-bg-secondary)] border border-[var(--color-border)]
          text-[var(--color-text-primary)]
          focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]
          disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? 'border-[var(--color-error)]' : ''}
        `}
      >
        <option value="">{placeholder || 'Select...'}</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {formatLabel(opt)}
          </option>
        ))}
      </select>
    </FieldWrapper>
  )
}

// =============================================================================
// Checkbox Field
// =============================================================================

interface CheckboxFieldProps {
  name: string
  label?: string
  value: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
  error?: string
}

function CheckboxField({
  name,
  label,
  value,
  onChange,
  disabled,
  error,
}: CheckboxFieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          name={name}
          checked={value || false}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
        />
        <span className="text-sm text-[var(--color-text-primary)]">
          {label || formatLabel(name)}
        </span>
      </label>
      {error && <p className="text-xs text-[var(--color-error)]">{error}</p>}
    </div>
  )
}

// =============================================================================
// Date Field
// =============================================================================

interface DateFieldProps {
  name: string
  label?: string
  value: string | null
  onChange: (value: string | null) => void
  required?: boolean
  error?: string
  disabled?: boolean
}

function DateField({
  name,
  label,
  value,
  onChange,
  required,
  error,
  disabled,
}: DateFieldProps) {
  return (
    <FieldWrapper label={label || formatLabel(name)} required={required} error={error}>
      <input
        type="date"
        name={name}
        value={value || ''}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled}
        className={`
          w-full px-3 py-2 rounded-[var(--radius-md)]
          bg-[var(--color-bg-secondary)] border border-[var(--color-border)]
          text-[var(--color-text-primary)]
          focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]
          disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? 'border-[var(--color-error)]' : ''}
        `}
      />
    </FieldWrapper>
  )
}

// =============================================================================
// Chips Field (Multi-select as chips)
// =============================================================================

interface ChipsFieldProps {
  name: string
  label?: string
  value: string[]
  onChange: (value: string[]) => void
  required?: boolean
  error?: string
  disabled?: boolean
  options?: string[]
}

function ChipsField({
  name,
  label,
  value,
  onChange,
  required,
  error,
  disabled,
  options,
}: ChipsFieldProps) {
  const selected = value || []

  const toggleItem = (item: string) => {
    if (selected.includes(item)) {
      onChange(selected.filter((i) => i !== item))
    } else {
      onChange([...selected, item])
    }
  }

  // If no predefined options, show a simple text input that adds chips
  if (!options) {
    return (
      <FieldWrapper label={label || formatLabel(name)} required={required} error={error}>
        <div className="flex flex-wrap gap-2 p-2 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] min-h-[42px]">
          {selected.map((item) => (
            <motion.span
              key={item}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              className="inline-flex items-center gap-1 px-2 py-1 bg-[var(--color-accent-muted)] text-[var(--color-accent)] rounded-full text-sm"
            >
              {item}
              <button
                type="button"
                onClick={() => toggleItem(item)}
                disabled={disabled}
                className="hover:text-[var(--color-error)] disabled:opacity-50"
              >
                ×
              </button>
            </motion.span>
          ))}
          <input
            type="text"
            placeholder="Type and press Enter..."
            disabled={disabled}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                const input = e.currentTarget
                const val = input.value.trim()
                if (val && !selected.includes(val)) {
                  onChange([...selected, val])
                  input.value = ''
                }
              }
            }}
            className="flex-1 min-w-[120px] bg-transparent outline-none text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]"
          />
        </div>
      </FieldWrapper>
    )
  }

  // With predefined options, show clickable chips
  return (
    <FieldWrapper label={label || formatLabel(name)} required={required} error={error}>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <motion.button
            key={opt}
            type="button"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => toggleItem(opt)}
            disabled={disabled}
            className={`
              px-3 py-1.5 rounded-full text-sm transition-colors
              ${selected.includes(opt)
                ? 'bg-[var(--color-accent)] text-[var(--color-text-inverse)]'
                : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]'
              }
              disabled:opacity-50 disabled:cursor-not-allowed
            `}
          >
            {formatLabel(opt)}
          </motion.button>
        ))}
      </div>
    </FieldWrapper>
  )
}

// =============================================================================
// Helpers
// =============================================================================

function formatLabel(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
