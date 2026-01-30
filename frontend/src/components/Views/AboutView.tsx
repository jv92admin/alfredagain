import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

const features = [
  {
    icon: '💬',
    title: 'Chat with Alfred',
    description: 'Talk naturally — ask questions, give commands, or just brainstorm. Alfred understands context and remembers your conversation.',
    examples: ['"What can I make with chicken and rice?"', '"Add eggs to my shopping list"', '"Plan meals for next week"'],
  },
  {
    icon: '📦',
    title: 'Inventory',
    description: 'Track what\'s in your pantry and fridge. Alfred uses this to suggest recipes and knows when things might expire.',
    examples: ['Add items manually or via chat', 'See what\'s running low', 'Match recipes to what you have'],
  },
  {
    icon: '📖',
    title: 'Recipes',
    description: 'Save your favorite recipes or import them from the web. Alfred can parse 400+ recipe sites automatically.',
    examples: ['Import from AllRecipes, NYT Cooking, etc.', 'Create recipes via chat', 'Scale ingredients up or down'],
  },
  {
    icon: '📅',
    title: 'Meal Plans',
    description: 'Plan your week with linked recipes. Alfred can suggest plans based on your preferences and what\'s in stock.',
    examples: ['"Plan dinners for this week"', 'Drag and drop to rearrange', 'Auto-generate shopping lists'],
  },
  {
    icon: '🛒',
    title: 'Shopping List',
    description: 'Build shopping lists from recipes or add items directly. Check items off as you shop.',
    examples: ['"Add ingredients for pasta carbonara"', 'Group by store section', 'Share lists with family'],
  },
  {
    icon: '✅',
    title: 'Tasks',
    description: 'Kitchen to-dos beyond shopping — prep work, cleaning, restocking. Link tasks to meals or recipes.',
    examples: ['"Remind me to defrost chicken tomorrow"', 'Meal prep checklists', 'Recurring tasks'],
  },
]

const tips = [
  {
    emoji: '🎯',
    tip: 'Use @mentions to reference specific items',
    detail: 'Type @ in chat to search and select recipes, ingredients, or other items. Alfred gets the full context.',
  },
  {
    emoji: '🔗',
    tip: 'Import recipes from any URL',
    detail: 'Click the import button on the Recipes page and paste a link. Works with most recipe sites.',
  },
  {
    emoji: '🧠',
    tip: 'Alfred remembers your preferences',
    detail: 'Your dietary restrictions, favorite cuisines, and cooking style inform every suggestion.',
  },
  {
    emoji: '⚡',
    tip: 'Chat and UI work together',
    detail: 'Make changes in the app, then ask Alfred about them. Or do everything through chat — your choice.',
  },
]

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
}

export function AboutView() {
  return (
    <div className="min-h-full bg-[var(--color-bg-primary)]">
      {/* Hero */}
      <div className="bg-gradient-to-br from-[var(--color-accent)] to-[#a15d6b] text-white">
        <div className="max-w-4xl mx-auto px-6 py-12 md:py-16">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <h1 className="text-3xl md:text-4xl font-light tracking-wide mb-4">
              Meet Alfred
            </h1>
            <p className="text-lg md:text-xl opacity-90 max-w-2xl leading-relaxed">
              Your AI kitchen assistant. Manage inventory, find recipes, plan meals, 
              and build shopping lists — all through natural conversation or direct control.
            </p>
          </motion.div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Features Grid */}
        <motion.section
          variants={container}
          initial="hidden"
          animate="show"
          className="mb-16"
        >
          <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-6">
            What Alfred Can Do
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {features.map((feature) => (
              <motion.div
                key={feature.title}
                variants={item}
                className="bg-[var(--color-bg-elevated)] rounded-[var(--radius-lg)] p-5 border border-[var(--color-border)] shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-md)] transition-shadow"
              >
                <div className="flex items-start gap-4">
                  <span className="text-2xl">{feature.icon}</span>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-[var(--color-text-primary)] mb-1">
                      {feature.title}
                    </h3>
                    <p className="text-sm text-[var(--color-text-secondary)] mb-3 leading-relaxed">
                      {feature.description}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {feature.examples.map((ex, i) => (
                        <span
                          key={i}
                          className="text-xs bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)] px-2 py-1 rounded-[var(--radius-sm)]"
                        >
                          {ex}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.section>

        {/* Tips */}
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="mb-16"
        >
          <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-6">
            Pro Tips
          </h2>
          <div className="bg-[var(--color-bg-secondary)] rounded-[var(--radius-lg)] border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
            {tips.map((t) => (
              <div key={t.tip} className="p-4 flex items-start gap-3">
                <span className="text-xl">{t.emoji}</span>
                <div>
                  <p className="font-medium text-[var(--color-text-primary)]">{t.tip}</p>
                  <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">{t.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </motion.section>

        {/* CTA */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="text-center pb-8"
        >
          <div className="bg-[var(--color-accent-muted)] rounded-[var(--radius-xl)] p-8 border border-[var(--color-border-accent)]">
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2">
              Ready to get cooking?
            </h2>
            <p className="text-[var(--color-text-secondary)] mb-5">
              Head to Chat and tell Alfred what you need.
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-2 px-6 py-2.5 bg-[var(--color-accent)] text-white font-medium rounded-[var(--radius-md)] hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              <span>💬</span>
              <span>Start Chatting</span>
            </Link>
          </div>
        </motion.section>
      </div>
    </div>
  )
}
