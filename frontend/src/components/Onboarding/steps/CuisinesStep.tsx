import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { apiRequest } from '../../../lib/api'

interface CuisinesStepProps {
  onNext: () => void
  onBack: () => void
}

interface Cuisine {
  id: string
  label: string
  icon: string
}

export function CuisinesStep({ onNext, onBack }: CuisinesStepProps) {
  const [cuisines, setCuisines] = useState<Cuisine[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    loadCuisines()
  }, [])

  const loadCuisines = async () => {
    try {
      const response = await fetch('/api/onboarding/cuisines/options')
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const json = await response.json()
      // API returns {options: [...], max_selections: number}
      setCuisines(json.options || [])
    } catch (err) {
      console.error('Failed to load cuisines:', err)
      setError('Failed to load cuisines')
    } finally {
      setLoading(false)
    }
  }

  const toggleCuisine = (id: string) => {
    if (selected.includes(id)) {
      setSelected(selected.filter(c => c !== id))
    } else {
      setSelected([...selected, id])
    }
  }

  const handleSubmit = async () => {
    setSaving(true)
    setError('')

    try {
      await apiRequest('/api/onboarding/cuisines', {
        method: 'POST',
        body: JSON.stringify({
          cuisines: selected,
        }),
      })
      onNext()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
      setSaving(false)
    }
  }

  const handleSkip = () => {
    onNext()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          What cuisines do you love?
        </h2>
        <p className="text-[var(--color-text-muted)]">
          Pick your favorites. Alfred will prioritize these when suggesting recipes.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
          {error}
        </div>
      )}

      {/* Cuisine Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {cuisines.map((cuisine, idx) => (
          <motion.button
            key={cuisine.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.03 }}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => toggleCuisine(cuisine.id)}
            className={`
              p-4 rounded-[var(--radius-lg)] border text-center transition-all
              ${selected.includes(cuisine.id)
                ? 'bg-[var(--color-accent-muted)] border-[var(--color-accent)] shadow-md'
                : 'bg-[var(--color-bg-secondary)] border-[var(--color-border)] hover:border-[var(--color-text-muted)]'
              }
            `}
          >
            <div className="text-2xl mb-2">{cuisine.icon}</div>
            <div className="text-sm font-medium text-[var(--color-text-primary)]">
              {cuisine.label}
            </div>
          </motion.button>
        ))}
      </div>

      {/* Selection Counter */}
      {selected.length > 0 && (
        <div className="text-center text-sm text-[var(--color-accent)]">
          {selected.length} cuisine{selected.length !== 1 ? 's' : ''} selected
        </div>
      )}

      {/* Buttons */}
      <div className="pt-4 flex justify-between">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onBack}
          className="px-6 py-3 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
        >
          ← Back
        </motion.button>
        <div className="flex gap-3">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleSkip}
            className="px-6 py-3 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            Skip
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleSubmit}
            disabled={saving || selected.length === 0}
            className="px-8 py-3 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-semibold rounded-[var(--radius-lg)] transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Continue'}
          </motion.button>
        </div>
      </div>
    </div>
  )
}
