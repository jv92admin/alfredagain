/**
 * StepsEditor - Ordered list editor for recipe instructions.
 *
 * Each row: step number | instruction text | move up/down | delete
 * Used within RecipeEditor for creating/editing recipes.
 */

import { motion, AnimatePresence, Reorder } from 'framer-motion'
import type { FieldRendererProps } from '../FieldRenderer'

// =============================================================================
// Types
// =============================================================================

interface StepsEditorProps extends Omit<FieldRendererProps, 'schema'> {
  value: string[]
  onChange: (value: string[]) => void
}

// =============================================================================
// StepsEditor Component
// =============================================================================

export function StepsEditor({
  name,
  label,
  value = [],
  onChange,
  disabled,
  error,
}: StepsEditorProps) {
  const steps = value || []

  const handleAdd = () => {
    onChange([...steps, ''])
  }

  const handleRemove = (index: number) => {
    onChange(steps.filter((_, i) => i !== index))
  }

  const handleUpdate = (index: number, text: string) => {
    onChange(steps.map((step, i) => (i === index ? text : step)))
  }

  const handleMoveUp = (index: number) => {
    if (index === 0) return
    const newSteps = [...steps]
    ;[newSteps[index - 1], newSteps[index]] = [newSteps[index], newSteps[index - 1]]
    onChange(newSteps)
  }

  const handleMoveDown = (index: number) => {
    if (index === steps.length - 1) return
    const newSteps = [...steps]
    ;[newSteps[index], newSteps[index + 1]] = [newSteps[index + 1], newSteps[index]]
    onChange(newSteps)
  }

  const handleReorder = (newOrder: string[]) => {
    onChange(newOrder)
  }

  const formatLabel = (str: string) =>
    str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div className="space-y-3">
      {label !== undefined && (
        <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
          {label || formatLabel(name)}
        </label>
      )}

      {steps.length === 0 ? (
        <div className="p-4 rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)] border border-dashed border-[var(--color-border)] text-center text-[var(--color-text-muted)] text-sm">
          No steps yet. Click "Add Step" to start.
        </div>
      ) : (
        <Reorder.Group
          axis="y"
          values={steps}
          onReorder={handleReorder}
          className="space-y-2"
        >
          <AnimatePresence mode="popLayout">
            {steps.map((step, index) => (
              <Reorder.Item
                key={`step-${index}-${step.slice(0, 10)}`}
                value={step}
                dragListener={!disabled}
              >
                <StepRow
                  step={step}
                  index={index}
                  total={steps.length}
                  onUpdate={(text) => handleUpdate(index, text)}
                  onRemove={() => handleRemove(index)}
                  onMoveUp={() => handleMoveUp(index)}
                  onMoveDown={() => handleMoveDown(index)}
                  disabled={disabled}
                />
              </Reorder.Item>
            ))}
          </AnimatePresence>
        </Reorder.Group>
      )}

      <motion.button
        type="button"
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        onClick={handleAdd}
        disabled={disabled}
        className="w-full px-4 py-2 rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        + Add Step
      </motion.button>

      {error && <p className="text-xs text-[var(--color-error)]">{error}</p>}
    </div>
  )
}

// =============================================================================
// StepRow Component
// =============================================================================

interface StepRowProps {
  step: string
  index: number
  total: number
  onUpdate: (text: string) => void
  onRemove: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  disabled?: boolean
}

function StepRow({
  step,
  index,
  total,
  onUpdate,
  onRemove,
  onMoveUp,
  onMoveDown,
  disabled,
}: StepRowProps) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="flex items-start gap-2 p-3 rounded-[var(--radius-md)] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] group"
    >
      {/* Drag handle */}
      <div
        className="mt-2 cursor-grab active:cursor-grabbing text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
        title="Drag to reorder"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 8h16M4 16h16"
          />
        </svg>
      </div>

      {/* Step number badge */}
      <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-full bg-[var(--color-accent-muted)] text-[var(--color-accent)] text-xs font-medium mt-1.5">
        {index + 1}
      </span>

      {/* Step text */}
      <textarea
        value={step}
        onChange={(e) => onUpdate(e.target.value)}
        placeholder={`Step ${index + 1}: Describe what to do...`}
        disabled={disabled}
        rows={2}
        className="flex-1 px-3 py-2 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-[var(--color-text-primary)] text-sm placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)] resize-y disabled:opacity-50 disabled:cursor-not-allowed"
      />

      {/* Actions */}
      <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {/* Move up */}
        <button
          type="button"
          onClick={onMoveUp}
          disabled={disabled || index === 0}
          className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-accent)] disabled:opacity-30 transition-colors"
          title="Move up"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 15l7-7 7 7"
            />
          </svg>
        </button>

        {/* Move down */}
        <button
          type="button"
          onClick={onMoveDown}
          disabled={disabled || index === total - 1}
          className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-accent)] disabled:opacity-30 transition-colors"
          title="Move down"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </button>

        {/* Remove */}
        <button
          type="button"
          onClick={onRemove}
          disabled={disabled}
          className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors disabled:opacity-50"
          title="Remove step"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>
    </motion.div>
  )
}

export default StepsEditor
