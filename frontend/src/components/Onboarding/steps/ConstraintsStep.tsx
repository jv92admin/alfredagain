import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { apiRequest } from '../../../lib/api'

interface ConstraintsStepProps {
  onNext: () => void
}

interface FormOptions {
  dietary_restrictions: string[]
  allergens: string[]
  skill_levels: { id: string; label: string; description: string }[]
  equipment: { id: string; label: string; icon: string }[]
}

export function ConstraintsStep({ onNext }: ConstraintsStepProps) {
  const [options, setOptions] = useState<FormOptions | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Form state
  const [householdSize, setHouseholdSize] = useState(2)
  const [dietary, setDietary] = useState<string[]>([])
  const [allergens, setAllergens] = useState<string[]>([])
  const [skill, setSkill] = useState('intermediate')
  const [equipment, setEquipment] = useState<string[]>([])

  useEffect(() => {
    loadOptions()
  }, [])

  const loadOptions = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/onboarding/constraints/options')
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const json = await response.json()
      setOptions(json)
    } catch (err) {
      console.error('Failed to load constraint options:', err)
      setError('Failed to load options. Please refresh the page.')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async () => {
    setSaving(true)
    setError('')

    try {
      await apiRequest('/api/onboarding/constraints', {
        method: 'POST',
        body: JSON.stringify({
          household_size: householdSize,
          dietary_restrictions: dietary,
          allergies: allergens,
          cooking_skill_level: skill,
          available_equipment: equipment,
        }),
      })
      onNext()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
      setSaving(false)
    }
  }

  const toggleItem = (list: string[], setList: (v: string[]) => void, item: string) => {
    if (list.includes(item)) {
      setList(list.filter(i => i !== item))
    } else {
      setList([...list, item])
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    )
  }

  if (!options) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-4">
        <div className="text-[var(--color-error)]">{error || 'Failed to load options'}</div>
        <button
          onClick={loadOptions}
          className="px-4 py-2 bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded-[var(--radius-md)]"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          Tell us about yourself
        </h2>
        <p className="text-[var(--color-text-muted)]">
          This helps Alfred tailor recipes and suggestions to you.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
          {error}
        </div>
      )}

      {/* Household Size */}
      <section>
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
          Household Size
        </h3>
        <div className="flex items-center gap-4">
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setHouseholdSize(Math.max(1, householdSize - 1))}
            disabled={householdSize <= 1}
            className="w-12 h-12 rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-xl font-bold text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] disabled:opacity-30"
          >
            −
          </motion.button>
          <div className="flex-1 text-center">
            <span className="text-4xl font-bold text-[var(--color-text-primary)]">{householdSize}</span>
            <span className="ml-2 text-[var(--color-text-muted)]">
              {householdSize === 1 ? 'person' : 'people'}
            </span>
          </div>
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setHouseholdSize(Math.min(12, householdSize + 1))}
            disabled={householdSize >= 12}
            className="w-12 h-12 rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-xl font-bold text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] disabled:opacity-30"
          >
            +
          </motion.button>
        </div>
        <p className="mt-2 text-sm text-[var(--color-text-muted)] text-center">
          Who are you cooking for?
        </p>
      </section>

      {/* Skill Level */}
      <section>
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
          Cooking Skill
        </h3>
        <div className="grid gap-3">
          {options.skill_levels.map(level => (
            <motion.button
              key={level.id}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              onClick={() => setSkill(level.id)}
              className={`
                p-4 rounded-[var(--radius-lg)] border text-left transition-colors
                ${skill === level.id
                  ? 'bg-[var(--color-accent-muted)] border-[var(--color-accent)]'
                  : 'bg-[var(--color-bg-secondary)] border-[var(--color-border)] hover:border-[var(--color-text-muted)]'
                }
              `}
            >
              <div className="font-medium text-[var(--color-text-primary)]">{level.label}</div>
              <div className="text-sm text-[var(--color-text-muted)] mt-1">{level.description}</div>
            </motion.button>
          ))}
        </div>
      </section>

      {/* Dietary Restrictions */}
      <section>
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
          Dietary Restrictions
        </h3>
        <div className="flex flex-wrap gap-2">
          {options.dietary_restrictions.map(restriction => (
            <motion.button
              key={restriction}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => toggleItem(dietary, setDietary, restriction)}
              className={`
                px-4 py-2 rounded-full text-sm transition-colors capitalize
                ${dietary.includes(restriction)
                  ? 'bg-[var(--color-accent)] text-[var(--color-text-inverse)]'
                  : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]'
                }
              `}
            >
              {restriction.replace('-', ' ')}
            </motion.button>
          ))}
        </div>
      </section>

      {/* Allergens */}
      <section>
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
          Allergies
        </h3>
        <div className="flex flex-wrap gap-2">
          {options.allergens.map(allergen => (
            <motion.button
              key={allergen}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => toggleItem(allergens, setAllergens, allergen)}
              className={`
                px-4 py-2 rounded-full text-sm transition-colors capitalize
                ${allergens.includes(allergen)
                  ? 'bg-[var(--color-error)] text-white'
                  : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]'
                }
              `}
            >
              {allergen}
            </motion.button>
          ))}
        </div>
      </section>

      {/* Equipment */}
      <section>
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
          Kitchen Equipment
        </h3>
        <div className="flex flex-wrap gap-2">
          {options.equipment.map(equip => (
            <motion.button
              key={equip.id}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => toggleItem(equipment, setEquipment, equip.id)}
              className={`
                px-4 py-2 rounded-full text-sm transition-colors
                ${equipment.includes(equip.id)
                  ? 'bg-[var(--color-success)] text-white'
                  : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]'
                }
              `}
            >
              {equip.icon} {equip.label}
            </motion.button>
          ))}
        </div>
      </section>

      {/* Continue Button */}
      <div className="pt-4 flex justify-end">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleSubmit}
          disabled={saving}
          className="px-8 py-3 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-semibold rounded-[var(--radius-lg)] transition-colors disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Continue'}
        </motion.button>
      </div>
    </div>
  )
}
