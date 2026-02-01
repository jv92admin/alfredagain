import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const fadeIn = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
}

const stagger = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
}

const viewport = { once: true, margin: '-40px' as const }

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

const NOT_LIST = [
  'Not a chatbot you have to talk to',
  'Not a recipe generator that ignores what you have',
  'Not an AI that decides what you should eat',
]

// ---------------------------------------------------------------------------
// AboutView
// ---------------------------------------------------------------------------

export function AboutView() {
  const prefersReduced = useReducedMotion()
  const dur = prefersReduced ? 0 : 0.4

  return (
    <div className="min-h-full bg-[var(--color-bg-primary)]">

      {/* ----------------------------------------------------------------- */}
      {/* 1. Hero                                                           */}
      {/* ----------------------------------------------------------------- */}
      <section className="bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-berry)] text-white">
        <div className="max-w-5xl mx-auto px-6 py-14 md:py-20">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: dur }}
          >
            <span className="inline-block text-xs tracking-widest uppercase opacity-70 mb-4 border border-white/30 rounded-full px-3 py-1">
              built as a personal project
            </span>
            <h1 className="text-3xl md:text-5xl font-light tracking-wide mb-4 leading-tight">
              cook more. think less.
            </h1>
            <p className="text-lg md:text-xl opacity-90 max-w-xl leading-relaxed">
              Alfred handles the planning, shopping, and logistics so you can just cook.
            </p>
          </motion.div>
        </div>
      </section>

      {/* ----------------------------------------------------------------- */}
      {/* 2. Problem                                                        */}
      {/* ----------------------------------------------------------------- */}
      <motion.section
        initial="hidden"
        whileInView="show"
        viewport={viewport}
        variants={stagger}
        className="max-w-5xl mx-auto px-6 py-16"
        aria-labelledby="about-problem"
      >
        <motion.h2
          id="about-problem"
          variants={fadeIn}
          className="text-2xl md:text-3xl font-light text-[var(--color-text-primary)] mb-8"
        >
          recipes aren't the hard part.
        </motion.h2>

        <div className="grid md:grid-cols-2 gap-6">
          <motion.div
            variants={fadeIn}
            className="bg-[var(--color-bg-secondary)] rounded-[var(--radius-xl)] p-6 border border-[var(--color-border)]"
          >
            <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-3">
              The chaos
            </h3>
            <p className="text-[var(--color-text-secondary)] leading-relaxed">
              Fifteen browser tabs. A notes app. A group chat. A fridge you forgot to check.
              Every week, same scramble.
            </p>
          </motion.div>

          <motion.div
            variants={fadeIn}
            className="bg-[var(--color-bg-elevated)] rounded-[var(--radius-xl)] p-6 border border-[var(--color-border-accent)]"
          >
            <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-accent)] mb-3">
              The calm
            </h3>
            <p className="text-[var(--color-text-secondary)] leading-relaxed">
              One place for recipes, plans, and shopping. Connected so you don't have to.
            </p>
          </motion.div>
        </div>
      </motion.section>

      {/* ----------------------------------------------------------------- */}
      {/* 3. Capabilities link                                              */}
      {/* ----------------------------------------------------------------- */}
      <motion.section
        initial="hidden"
        whileInView="show"
        viewport={viewport}
        variants={stagger}
        className="max-w-5xl mx-auto px-6 pb-16"
      >
        <motion.div variants={fadeIn}>
          <Link
            to="/capabilities"
            className="block bg-[var(--color-bg-elevated)] rounded-[var(--radius-xl)] p-6 border border-[var(--color-border)] hover:border-[var(--color-accent)] transition-colors group"
          >
            <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2 group-hover:text-[var(--color-accent)] transition-colors">
              See what Alfred can do &rarr;
            </h3>
            <p className="text-sm text-[var(--color-text-muted)]">
              Recipes, meal planning, shopping lists, cook mode, and more.
            </p>
          </Link>
        </motion.div>
      </motion.section>

      {/* ----------------------------------------------------------------- */}
      {/* 4. Not AI-First                                                   */}
      {/* ----------------------------------------------------------------- */}
      <motion.section
        initial="hidden"
        whileInView="show"
        viewport={viewport}
        variants={stagger}
        className="bg-[var(--color-bg-secondary)] py-16"
        aria-labelledby="about-not-ai"
      >
        <div className="max-w-5xl mx-auto px-6">
          <motion.h2
            id="about-not-ai"
            variants={fadeIn}
            className="text-2xl md:text-3xl font-light text-[var(--color-text-primary)] mb-8"
          >
            alfred isn't trying to replace your brain.
          </motion.h2>

          <div className="space-y-3 mb-6">
            {NOT_LIST.map((item) => (
              <motion.div
                key={item}
                variants={fadeIn}
                className="flex items-center gap-3 text-[var(--color-text-secondary)]"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-text-muted)] flex-shrink-0" />
                {item}
              </motion.div>
            ))}
          </div>

          <motion.p
            variants={fadeIn}
            className="text-[var(--color-text-primary)] font-medium leading-relaxed"
          >
            It does the tedious parts so you can focus on cooking.
          </motion.p>
        </div>
      </motion.section>

      {/* ----------------------------------------------------------------- */}
      {/* 5. Maker Note                                                     */}
      {/* ----------------------------------------------------------------- */}
      <motion.section
        initial="hidden"
        whileInView="show"
        viewport={viewport}
        variants={stagger}
        className="max-w-3xl mx-auto px-6 py-16"
        aria-labelledby="about-maker"
      >
        <motion.div variants={fadeIn}>
          <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
            I built Alfred because I wanted to cook more and plan less. It started as a
            weekend project and turned into something I use every day. It's not finished —
            it probably never will be. But it works for me, and I think it might work for
            you too.
          </p>
          <p className="text-[var(--color-text-primary)] font-medium">
            — V
          </p>
        </motion.div>
      </motion.section>

      {/* ----------------------------------------------------------------- */}
      {/* 6. CTA                                                            */}
      {/* ----------------------------------------------------------------- */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: dur, delay: 0.1 }}
        className="max-w-3xl mx-auto px-6 pb-12 text-center"
      >
        <div className="bg-[var(--color-accent-muted)] rounded-[var(--radius-xl)] p-8 border border-[var(--color-border-accent)]">
          <p className="text-[var(--color-text-secondary)] mb-5">
            Want to try it?
          </p>
          <Link
            to="/home"
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-[var(--color-accent)] text-white font-medium rounded-[var(--radius-md)] hover:bg-[var(--color-accent-hover)] transition-colors"
          >
            Get Started
          </Link>
        </div>
      </motion.section>

    </div>
  )
}
