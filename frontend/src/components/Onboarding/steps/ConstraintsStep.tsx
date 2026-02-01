import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { apiRequest } from '../../../lib/api'

interface ConstraintsStepProps {
  onNext: () => void
}

interface EquipmentOption {
  id: string
  label: string
  icon: string
}

interface FormOptions {
  dietary_restrictions: string[]
  allergens: string[]
  skill_levels: { id: string; label: string; description: string }[]
  equipment: EquipmentOption[]
  basic_equipment: EquipmentOption[]
  specialty_equipment: EquipmentOption[]
  default_selected_equipment: string[]
}

export function ConstraintsStep({ onNext }: ConstraintsStepProps) {
  const [options, setOptions] = useState<FormOptions | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Form state
  const [adults, setAdults] = useState(2)
  const [kids, setKids] = useState(0)
  const [babies, setBabies] = useState(0)
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
      // Pre-select basic equipment for new users
      if (json.default_selected_equipment) {
        setEquipment(json.default_selected_equipment)
      }
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
          household_adults: adults,
          household_kids: kids,
          household_babies: babies,
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

  const portions = adults + kids * 0.5

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

      {/* Household */}
      <section>
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
          Who are you cooking for?
        </h3>
        <div className="grid grid-cols-3 gap-4">
          <Counter label="Adults" value={adults} onChange={setAdults} min={0} max={12} />
          <Counter label="Kids" value={kids} onChange={setKids} min={0} max={12} />
          <Counter label="Babies" value={babies} onChange={setBabies} min={0} max={12} />
        </div>
        {(adults + kids + babies) > 0 && (
          <p className="mt-2 text-sm text-[var(--color-text-muted)] text-center">
            ~{portions % 1 === 0 ? portions : portions.toFixed(1)} portions per meal
          </p>
        )}
        {(adults + kids + babies) === 0 && (
          <p className="mt-2 text-sm text-[var(--color-error)] text-center">
            At least 1 person required
          </p>
        )}
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

      {/* Equipment - Basics */}
      <section>
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
          Kitchen Basics
        </h3>
        <p className="text-xs text-[var(--color-text-muted)] mb-2">
          Uncheck anything you don't have
        </p>
        <div className="flex flex-wrap gap-2">
          {options.basic_equipment.map(equip => (
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

      {/* Equipment - Specialty */}
      <section>
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 uppercase tracking-wide">
          Specialty Equipment
        </h3>
        <div className="flex flex-wrap gap-2">
          {options.specialty_equipment.map(equip => (
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
          disabled={saving || (adults + kids + babies) === 0}
          className="px-8 py-3 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-semibold rounded-[var(--radius-lg)] transition-colors disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Continue'}
        </motion.button>
      </div>
    </div>
  )
}

function Counter({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min: number
  max: number
}) {
  return (
    <div className="flex flex-col items-center gap-2">
      <span className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide">{label}</span>
      <div className="flex items-center gap-3">
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => onChange(Math.max(min, value - 1))}
          disabled={value <= min}
          className="w-9 h-9 rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-lg font-bold text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] disabled:opacity-30"
        >
          −
        </motion.button>
        <span className="text-2xl font-bold text-[var(--color-text-primary)] w-8 text-center">{value}</span>
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => onChange(Math.min(max, value + 1))}
          disabled={value >= max}
          className="w-9 h-9 rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-lg font-bold text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] disabled:opacity-30"
        >
          +
        </motion.button>
      </div>
    </div>
  )
}
