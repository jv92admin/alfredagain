import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { RecipeImportModal } from '../Recipe'

interface DashboardCounts {
  recipes: number
  inventory: number
  shopping: number
  meals: number
  tasks: number
}

interface Nudge {
  key: string
  title: string
  description: string
  primaryLabel: string
  primaryAction: () => void
  secondaryLabel?: string
  secondaryAction?: () => void
}

const STAT_CARDS = [
  { key: 'recipes', label: 'Recipes', path: '/recipes' },
  { key: 'inventory', label: 'Pantry', path: '/inventory' },
  { key: 'shopping', label: 'Shopping', path: '/shopping' },
  { key: 'meals', label: 'Meals', path: '/meals' },
  { key: 'tasks', label: 'Tasks', path: '/tasks' },
] as const

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 12) return 'Good morning!'
  if (hour >= 12 && hour < 17) return 'Good afternoon!'
  if (hour >= 17 && hour < 21) return 'Good evening!'
  return 'Hey there!'
}

function StatCard({ label, count, path, index }: { label: string; count: number; path: string; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.05 }}
    >
      <Link
        to={path}
        className="block bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 hover:border-[var(--color-accent)] transition-colors text-center"
      >
        <div className="text-2xl font-semibold text-[var(--color-accent)]">
          {count}
        </div>
        <div className="text-sm text-[var(--color-text-muted)] mt-1">
          {label}
        </div>
      </Link>
    </motion.div>
  )
}

function NudgeCard({ nudge }: { nudge: Nudge }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.3 }}
      className="bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6"
    >
      <h3 className="text-base font-semibold text-[var(--color-text-primary)] mb-2">
        {nudge.title}
      </h3>
      <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed mb-4 whitespace-pre-line">
        {nudge.description}
      </p>
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={nudge.primaryAction}
          className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] text-sm font-medium rounded-[var(--radius-md)] transition-colors"
        >
          {nudge.primaryLabel}
        </button>
        {nudge.secondaryLabel && nudge.secondaryAction && (
          <button
            onClick={nudge.secondaryAction}
            className="px-4 py-2 border border-[var(--color-border)] hover:border-[var(--color-accent)] text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] rounded-[var(--radius-md)] transition-colors"
          >
            {nudge.secondaryLabel}
          </button>
        )}
      </div>
    </motion.div>
  )
}

export function HomeView() {
  const navigate = useNavigate()
  const [counts, setCounts] = useState<DashboardCounts>({
    recipes: 0, inventory: 0, shopping: 0, meals: 0, tasks: 0,
  })
  const [loading, setLoading] = useState(true)
  const [showImportModal, setShowImportModal] = useState(false)

  useEffect(() => {
    fetchCounts()
  }, [])

  const fetchCounts = async () => {
    const tables = ['recipes', 'inventory', 'shopping_list', 'meal_plans', 'tasks'] as const
    const keys: (keyof DashboardCounts)[] = ['recipes', 'inventory', 'shopping', 'meals', 'tasks']

    const results = await Promise.allSettled(
      tables.map(t => apiRequest<{ data: unknown[]; count: number }>(`/api/entities/${t}`))
    )

    const newCounts: DashboardCounts = { recipes: 0, inventory: 0, shopping: 0, meals: 0, tasks: 0 }
    results.forEach((result, i) => {
      if (result.status === 'fulfilled') {
        newCounts[keys[i]] = result.value.data?.length ?? result.value.count ?? 0
      }
    })

    setCounts(newCounts)
    setLoading(false)
  }

  const goToChat = (prompt: string) => {
    navigate('/', { state: { prefillPrompt: prompt } })
  }

  const computeNudges = (): Nudge[] => {
    const nudges: Nudge[] = []

    if (counts.recipes === 0) {
      nudges.push({
        key: 'first-recipe',
        title: 'Get your first recipe',
        description:
          'Tell Alfred what you\u2019re in the mood for \u2014 it\u2019ll draft something based on your pantry and preferences.',
        primaryLabel: 'Ask Alfred to Create',
        primaryAction: () => goToChat('Suggest a simple dinner recipe using my current pantry'),
        secondaryLabel: 'Import from URL',
        secondaryAction: () => setShowImportModal(true),
      })
    }

    if (counts.inventory < 10) {
      nudges.push({
        key: 'stock-pantry',
        title: 'Your Pantry',
        description:
          'Alfred works best when it knows what you have. This powers:\n' +
          '\u2022 Recipe suggestions that use your actual ingredients\n' +
          '\u2022 Shopping lists that skip what you already own\n' +
          '\u2022 Meal plans that minimize waste\n\n' +
          'Start with staples, add as you shop.',
        primaryLabel: 'Add Pantry Items',
        primaryAction: () => navigate('/inventory'),
        secondaryLabel: 'Learn more',
        secondaryAction: () => navigate('/capabilities#inventory'),
      })
    }

    if (counts.recipes > 5 && counts.meals === 0) {
      nudges.push({
        key: 'plan-week',
        title: 'Plan your week',
        description:
          `You have ${counts.recipes} recipes saved. Pick which days you want to cook and Alfred will help you choose recipes that work together.`,
        primaryLabel: 'Plan Meals',
        primaryAction: () => goToChat('Help me plan 4 dinners for this week using my saved recipes'),
        secondaryLabel: 'Learn more',
        secondaryAction: () => navigate('/capabilities#meal-planning'),
      })
    }

    if (counts.meals > 0 && counts.shopping === 0) {
      nudges.push({
        key: 'shopping-list',
        title: 'Build your shopping list',
        description:
          'Your meal plan is set. Alfred can generate a shopping list and cross-reference your pantry so you skip what you already have.',
        primaryLabel: 'Generate Shopping List',
        primaryAction: () => goToChat('Build a shopping list for my planned meals'),
        secondaryLabel: 'Learn more',
        secondaryAction: () => navigate('/capabilities#shopping'),
      })
    }

    return nudges.slice(0, 2)
  }

  const nudges = loading ? [] : computeNudges()
  const allSet = !loading && nudges.length === 0

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Greeting */}
      <motion.h1
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="text-2xl font-semibold text-[var(--color-text-primary)] mb-6"
      >
        {getGreeting()}
      </motion.h1>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-8">
        {STAT_CARDS.map((card, i) => (
          <StatCard
            key={card.key}
            label={card.label}
            count={loading ? 0 : counts[card.key]}
            path={card.path}
            index={i}
          />
        ))}
      </div>

      {/* Nudge Cards */}
      {nudges.length > 0 && (
        <div className="space-y-4 mb-8">
          {nudges.map((nudge) => (
            <NudgeCard key={nudge.key} nudge={nudge} />
          ))}
        </div>
      )}

      {/* All set state */}
      {allSet && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.3 }}
          className="bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6 text-center mb-8"
        >
          <p className="text-sm text-[var(--color-text-secondary)] mb-3">
            You&rsquo;re all set! Ask Alfred anything.
          </p>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] text-sm font-medium rounded-[var(--radius-md)] transition-colors"
          >
            Chat with Alfred
          </button>
        </motion.div>
      )}

      {/* Quick Actions */}
      <div className="flex items-center gap-3 flex-wrap">
        <Link
          to="/"
          className="px-4 py-2 text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] border border-[var(--color-border)] hover:border-[var(--color-accent)] rounded-[var(--radius-md)] transition-colors"
        >
          Chat with Alfred
        </Link>
        <Link
          to="/capabilities"
          className="px-4 py-2 text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] border border-[var(--color-border)] hover:border-[var(--color-accent)] rounded-[var(--radius-md)] transition-colors"
        >
          What can Alfred do?
        </Link>
      </div>

      {/* Recipe Import Modal */}
      <RecipeImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onSuccess={() => {
          setShowImportModal(false)
          fetchCounts()
        }}
      />
    </div>
  )
}
