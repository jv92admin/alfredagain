import { motion } from 'framer-motion'

interface ChipOption {
  label: string
  value: string
}

interface ChipQuestionProps {
  question: string
  options: ChipOption[]
  multi?: boolean
  value: string | null
  values: string[]
  onChange: (value: string | null, values: string[]) => void
}

export function ChipQuestion({
  question,
  options,
  multi = false,
  value,
  values,
  onChange,
}: ChipQuestionProps) {
  const handleClick = (optionValue: string) => {
    if (multi) {
      const newValues = values.includes(optionValue)
        ? values.filter(v => v !== optionValue)
        : [...values, optionValue]
      onChange(null, newValues)
    } else {
      onChange(value === optionValue ? null : optionValue, [])
    }
  }

  const isSelected = (optionValue: string) =>
    multi ? values.includes(optionValue) : value === optionValue

  return (
    <div className="space-y-3">
      <label className="block text-[var(--color-text-primary)] font-medium">
        {question}
      </label>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <motion.button
            key={option.value}
            type="button"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => handleClick(option.value)}
            className={`
              px-4 py-2.5 rounded-[var(--radius-lg)] border text-sm
              transition-all cursor-pointer text-left
              ${isSelected(option.value)
                ? 'bg-[var(--color-accent-muted)] border-[var(--color-accent)] text-[var(--color-text-primary)] shadow-sm'
                : 'bg-[var(--color-bg-secondary)] border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-text-muted)]'
              }
            `}
          >
            {option.label}
          </motion.button>
        ))}
      </div>
      {multi && (
        <p className="text-xs text-[var(--color-text-muted)]">
          Select all that apply
        </p>
      )}
    </div>
  )
}
