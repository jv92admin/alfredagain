import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'

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

const STEPS = [
  {
    label: 'Import a recipe',
    caption: 'Paste a URL. Alfred pulls the ingredients and steps. Review it, tweak it, save it.',
    image: '/about/recipe-import.jpg',
    alt: 'Recipe import dialog showing a URL input and import button',
  },
  {
    label: 'Plan the week',
    caption: 'Pick a recipe, drop it into a day. Do as many or as few days as you want.',
    image: '/about/browse-panel.jpg',
    alt: 'Browse panel showing recipes, inventory, shopping list, and meal plans',
  },
  {
    label: 'Shopping falls out of the plan',
    caption: 'The list builds itself from your meals. Check things off as you go.',
    image: '/about/shopping-list.jpg',
    alt: 'Shopping list with pending and purchased items grouped by status',
  },
  {
    label: 'Life changes, plan adjusts',
    caption: 'Swap a meal, adjust a recipe, update the list — done.',
    image: '/about/chat-recipes.jpg',
    alt: 'Chat view showing Alfred listing stored recipes in conversation',
  },
]

const NOT_LIST = [
  'Not a chatbot you have to talk to',
  'Not a recipe generator that ignores what you have',
  'Not an AI that decides what you should eat',
]

// ---------------------------------------------------------------------------
// PhoneFrame
// ---------------------------------------------------------------------------

function PhoneFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative mx-auto max-w-[260px]">
      <div className="rounded-[2rem] border-[6px] border-[var(--color-text-primary)] bg-[var(--color-bg-elevated)] overflow-hidden shadow-[var(--shadow-lg)]">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-20 h-4 bg-[var(--color-text-primary)] rounded-b-xl z-10" />
        <div className="aspect-[9/19.5] overflow-hidden">
          {children}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AboutView
// ---------------------------------------------------------------------------

export function AboutView() {
  const [activeStep, setActiveStep] = useState(0)
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
      {/* 3. How It Works — Sticky Scrollytelling                           */}
      {/* ----------------------------------------------------------------- */}
      <section
        className="bg-[var(--color-bg-secondary)] py-16"
        aria-labelledby="about-how"
      >
        <div className="max-w-5xl mx-auto px-6">
          <motion.h2
            id="about-how"
            initial="hidden"
            whileInView="show"
            viewport={viewport}
            variants={fadeIn}
            className="text-2xl md:text-3xl font-light text-[var(--color-text-primary)] mb-12"
          >
            how it works
          </motion.h2>

          {/* Desktop: sticky two-column */}
          <div className="hidden md:flex gap-12">
            {/* Left: scrolling step cards */}
            <div className="w-1/2">
              {STEPS.map((step, i) => (
                <motion.div
                  key={i}
                  className="min-h-[80vh] flex items-center"
                  onViewportEnter={() => setActiveStep(i)}
                  viewport={{ amount: 0.5 }}
                >
                  <div>
                    <span className="text-sm font-semibold text-[var(--color-accent)] mb-2 block">
                      Step {i + 1}
                    </span>
                    <h3 className="text-xl font-medium text-[var(--color-text-primary)] mb-3">
                      {step.label}
                    </h3>
                    <p className="text-[var(--color-text-secondary)] leading-relaxed max-w-sm">
                      {step.caption}
                    </p>
                  </div>
                </motion.div>
              ))}
            </div>

            {/* Right: sticky phone frame */}
            <div className="w-1/2 self-start sticky top-[calc(50vh-300px)]">
              <PhoneFrame>
                <AnimatePresence mode="wait">
                  <motion.img
                    key={activeStep}
                    src={STEPS[activeStep].image}
                    alt={STEPS[activeStep].alt}
                    className="w-full h-full object-cover object-top"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: prefersReduced ? 0 : 0.3 }}
                  />
                </AnimatePresence>
              </PhoneFrame>
            </div>
          </div>

          {/* Mobile: stacked */}
          <div className="md:hidden space-y-14">
            {STEPS.map((step, i) => (
              <motion.div
                key={i}
                initial="hidden"
                whileInView="show"
                viewport={viewport}
                variants={stagger}
              >
                <motion.div variants={fadeIn} className="mb-6">
                  <span className="text-sm font-semibold text-[var(--color-accent)] mb-1 block">
                    Step {i + 1}
                  </span>
                  <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">
                    {step.label}
                  </h3>
                  <p className="text-[var(--color-text-secondary)] leading-relaxed">
                    {step.caption}
                  </p>
                </motion.div>
                <motion.div variants={fadeIn}>
                  <PhoneFrame>
                    <img
                      src={step.image}
                      alt={step.alt}
                      className="w-full h-full object-cover object-top"
                    />
                  </PhoneFrame>
                </motion.div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------------------- */}
      {/* 4. Assistant                                                      */}
      {/* ----------------------------------------------------------------- */}
      <motion.section
        initial="hidden"
        whileInView="show"
        viewport={viewport}
        variants={stagger}
        className="max-w-5xl mx-auto px-6 py-16"
        aria-labelledby="about-assistant"
      >
        <motion.h2
          id="about-assistant"
          variants={fadeIn}
          className="text-2xl md:text-3xl font-light text-[var(--color-text-primary)] mb-6"
        >
          the assistant handles the annoying logistics.
        </motion.h2>

        <div className="grid md:grid-cols-2 gap-10 items-center">
          <motion.div variants={fadeIn}>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-6">
              You can use Alfred by clicking around like a normal app — or just tell it
              what you want to happen. Point at real things with @-mentions so the
              system knows exactly what you mean.
            </p>
            <div className="bg-[var(--color-bg-secondary)] rounded-[var(--radius-lg)] p-4 border border-[var(--color-border)] mb-4">
              <p className="text-[var(--color-text-primary)] text-sm italic leading-relaxed">
                "move <span className="text-[var(--color-accent)] font-medium">@thai curry</span> to
                friday, make it vegetarian, and add what i'm missing."
              </p>
            </div>
            <p className="text-sm text-[var(--color-text-muted)]">
              Nothing gets saved without you saying so.
            </p>
          </motion.div>

          <motion.div variants={fadeIn}>
            <PhoneFrame>
              <img
                src="/about/at-mention.jpg"
                alt="@-mention autocomplete showing matching recipes, inventory items, and shopping list entries"
                className="w-full h-full object-cover object-top"
              />
            </PhoneFrame>
          </motion.div>
        </div>
      </motion.section>

      {/* ----------------------------------------------------------------- */}
      {/* 5. Not AI-First                                                   */}
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
      {/* 6. Maker Note                                                     */}
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
      {/* 7. CTA                                                            */}
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
            to="/"
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-[var(--color-accent)] text-white font-medium rounded-[var(--radius-md)] hover:bg-[var(--color-accent-hover)] transition-colors"
          >
            Get Started
          </Link>
        </div>
      </motion.section>

    </div>
  )
}
