import { useEffect } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'

interface CapabilitySection {
  id: string
  title: string
  content: string
  linkTo: string | null
  linkLabel: string | null
  tryPrompt: string | null
}

const SECTIONS: CapabilitySection[] = [
  {
    id: 'recipe-import',
    title: 'Getting Recipes',
    content:
      'Three ways to build your collection:\n\n' +
      '\u2022 **Import from URL** \u2014 paste a link from AllRecipes, Serious Eats, NYT Cooking, or 400+ other sites. Alfred extracts the recipe automatically.\n' +
      '\u2022 **Create manually** \u2014 use the recipe editor for family recipes or ones you know by heart.\n' +
      '\u2022 **Ask Alfred** \u2014 describe what you want and Alfred drafts a recipe based on your pantry and preferences.',
    linkTo: '/recipes',
    linkLabel: 'Go to Recipes',
    tryPrompt: 'I\u2019d like to create some simple recipes based on what I have and my preferences. I can go grocery shopping later for any ingredients I might need.',
  },
  {
    id: 'inventory',
    title: 'Your Pantry',
    content:
      'Alfred works best when it knows what you have. This powers:\n\n' +
      '\u2022 Recipe suggestions that use your actual ingredients\n' +
      '\u2022 Shopping lists that skip what you already own\n' +
      '\u2022 Meal plans that minimize waste\n\n' +
      'Start with staples, add as you shop. You can tell Alfred what you have in plain language and it\u2019ll add everything for you.',
    linkTo: '/inventory',
    linkLabel: 'Go to Inventory',
    tryPrompt: 'Can you add the following to my inventory: ',
  },
  {
    id: 'meal-planning',
    title: 'Meal Planning',
    content:
      'Plan your week by assigning recipes to days. Alfred tracks what\u2019s planned and can build your shopping list from the plan. ' +
      'Tell Alfred which days you want to cook, whether you like to meal prep, and it\u2019ll put together a plan that works.',
    linkTo: '/meals',
    linkLabel: 'Go to Meal Plans',
    tryPrompt: 'Can you plan a week\u2019s worth of dinners for me? I can meal prep on Sunday.',
  },
  {
    id: 'shopping',
    title: 'Shopping Lists',
    content:
      'Auto-generate a shopping list from your meal plan, or add items manually. ' +
      'Alfred cross-references your inventory so you don\u2019t buy what you already have.',
    linkTo: '/shopping',
    linkLabel: 'Go to Shopping',
    tryPrompt: 'Can you look at my meal plan for the next 5 days and add the missing stuff to my shopping list?',
  },
  {
    id: 'cook-mode',
    title: 'Cook Mode',
    content:
      'Hands-free, step-by-step cooking guidance. Select a recipe, enter cook mode, and Alfred walks you through each step. ' +
      'Ask questions as you go \u2014 substitutions, timing, technique \u2014 without losing your place.',
    linkTo: null,
    linkLabel: null,
    tryPrompt: null,
  },
  {
    id: 'mentions',
    title: '@Mentions',
    content:
      'Point Alfred at exactly what you mean by typing @ in the chat input. ' +
      'Reference a saved recipe, an inventory item, or a shopping list item. ' +
      'This gives Alfred precise context so it can help more accurately.',
    linkTo: null,
    linkLabel: null,
    tryPrompt: null,
  },
]

function CapabilityCard({ section }: { section: CapabilitySection }) {
  const navigate = useNavigate()

  const startChatWithPrompt = (prompt: string) => {
    navigate('/', { state: { prefillPrompt: prompt } })
  }

  return (
    <motion.section
      id={section.id}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.3 }}
      className="bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6 scroll-mt-6"
    >
      <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-3">
        {section.title}
      </h2>

      <div className="text-sm text-[var(--color-text-secondary)] leading-relaxed whitespace-pre-line">
        {section.content.split('\n').map((line, i) => {
          // Bold text between ** markers
          const parts = line.split(/(\*\*[^*]+\*\*)/)
          return (
            <span key={i}>
              {parts.map((part, j) =>
                part.startsWith('**') && part.endsWith('**') ? (
                  <strong key={j} className="text-[var(--color-text-primary)] font-medium">
                    {part.slice(2, -2)}
                  </strong>
                ) : (
                  <span key={j}>{part}</span>
                )
              )}
              {i < section.content.split('\n').length - 1 && <br />}
            </span>
          )
        })}
      </div>

      {section.linkTo && (
        <Link
          to={section.linkTo}
          className="inline-block mt-4 text-sm font-medium text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] transition-colors"
        >
          {section.linkLabel} &rarr;
        </Link>
      )}

      {section.tryPrompt && (
        <div className="mt-4 pt-4 border-t border-[var(--color-border)] flex items-center gap-3">
          <span className="text-sm text-[var(--color-text-muted)] italic flex-1 min-w-0 truncate">
            &ldquo;{section.tryPrompt}&rdquo;
          </span>
          <button
            onClick={() => startChatWithPrompt(section.tryPrompt!)}
            className="flex-shrink-0 px-3 py-1.5 text-sm font-medium text-[var(--color-accent)] border border-[var(--color-accent)] rounded-[var(--radius-md)] hover:bg-[var(--color-accent-muted)] transition-colors"
          >
            Try &rarr;
          </button>
        </div>
      )}
    </motion.section>
  )
}

export function CapabilitiesView() {
  const { hash } = useLocation()

  useEffect(() => {
    if (hash) {
      const el = document.getElementById(hash.slice(1))
      if (el) {
        // Small delay to let the page render before scrolling
        setTimeout(() => el.scrollIntoView({ behavior: 'smooth' }), 100)
      }
    }
  }, [hash])

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-semibold text-[var(--color-text-primary)] mb-2">
        What Alfred Can Do
      </h1>
      <p className="text-sm text-[var(--color-text-muted)] mb-8">
        Quick guides to help you cook more, think less.
      </p>

      <div className="space-y-4">
        {SECTIONS.map((section) => (
          <CapabilityCard key={section.id} section={section} />
        ))}
      </div>
    </div>
  )
}
