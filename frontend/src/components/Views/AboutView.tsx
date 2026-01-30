import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

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

const recentBuilds = [
  {
    title: 'Personalized onboarding',
    detail: 'A short setup to shape Alfred around how you cook.',
  },
  {
    title: '@ tagging',
    detail: 'Reference specific recipes, ingredients, or meals so the system knows exactly what you\'re talking about.',
  },
  {
    title: 'Recipe importing',
    detail: 'Paste in a recipe link and turn it into something you can plan, edit, and reuse.',
  },
]

export function AboutView() {
  return (
    <div className="min-h-full bg-[var(--color-bg-primary)]">
      {/* Hero */}
      <div className="bg-gradient-to-br from-[var(--color-accent)] to-[#a15d6b] text-white">
        <div className="max-w-3xl mx-auto px-6 py-12 md:py-16">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <h1 className="text-3xl md:text-4xl font-light tracking-wide mb-4">
              Alfred
            </h1>
            <p className="text-lg md:text-xl opacity-90 max-w-2xl leading-relaxed">
              A cooking and meal-planning app with an AI layer that helps with the logistics.
              The app handles the structure. The AI helps connect things and fill in the gaps.
            </p>
          </motion.div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-10">
        {/* Origin story */}
        <motion.section
          initial="hidden"
          animate="show"
          variants={stagger}
          className="mb-14"
        >
          <motion.div variants={fadeIn} className="prose-section">
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              I built Alfred because I like cooking, but I kept running into the same problems.
            </p>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              I wanted to cook more often, try new things, and make better use of what I already
              had. What kept getting in the way wasn't recipes — it was planning. Figuring out
              what to cook, whether I had the ingredients, what needed to be bought, and how it
              all fit into a week.
            </p>
            <p className="text-[var(--color-text-primary)] leading-relaxed font-medium">
              Alfred is the tool I ended up building for that.
            </p>
          </motion.div>
        </motion.section>

        {/* Creating Recipes */}
        <motion.section
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-40px' }}
          variants={stagger}
          className="mb-14"
        >
          <motion.h2 variants={fadeIn} className="text-xl font-semibold text-[var(--color-text-primary)] mb-4">
            Creating Recipes for Real Situations
          </motion.h2>
          <motion.div variants={fadeIn}>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              Most of the time, I'm not looking for "the best" recipe. I'm trying to cook
              something that fits a specific moment — what I have on hand, how much time I have,
              what I feel like eating, or what I've been cooking a lot lately.
            </p>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              Alfred helps me create recipes based on:
            </p>
            <ul className="space-y-2 mb-4">
              {['Ingredients I already have', 'My preferences', 'The context I\'m cooking in'].map((item) => (
                <li key={item} className="flex items-center gap-3 text-[var(--color-text-secondary)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] flex-shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
            <p className="text-[var(--color-text-secondary)] leading-relaxed">
              I also import recipes from the web and adjust them. Over time, this turns into a
              personal recipe collection that actually reflects how I cook.
            </p>
          </motion.div>
        </motion.section>

        {/* Meal Planning */}
        <motion.section
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-40px' }}
          variants={stagger}
          className="mb-14"
        >
          <motion.h2 variants={fadeIn} className="text-xl font-semibold text-[var(--color-text-primary)] mb-4">
            Meal Planning
          </motion.h2>
          <motion.div variants={fadeIn}>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              Meal planning is the part that makes everything else easier. When meals are planned,
              shopping is easier. Prep is easier. Cooking feels calmer. I end up eating better
              food more consistently.
            </p>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              In Alfred, meals link directly to recipes. From there, shopping lists and prep tasks
              fall out naturally. I can plan a few days or a full week and adjust things as plans change.
            </p>
            <p className="text-[var(--color-text-primary)] leading-relaxed font-medium">
              For me, this has been the biggest unlock for cooking at home more often.
            </p>
          </motion.div>
        </motion.section>

        {/* AI */}
        <motion.section
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-40px' }}
          variants={stagger}
          className="mb-14"
        >
          <motion.h2 variants={fadeIn} className="text-xl font-semibold text-[var(--color-text-primary)] mb-4">
            How the AI Fits In
          </motion.h2>
          <motion.div variants={fadeIn}>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              The AI isn't there to chat for the sake of chatting. It's there to help with:
            </p>
            <ul className="space-y-2 mb-4">
              {[
                'Creating recipes from context',
                'Adjusting plans',
                'Filling in gaps when something changes',
                'Reducing the manual work needed to keep things organized',
              ].map((item) => (
                <li key={item} className="flex items-center gap-3 text-[var(--color-text-secondary)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] flex-shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
            <p className="text-[var(--color-text-secondary)] leading-relaxed">
              The goal is for Alfred to remember enough context that you don't have to keep
              restating things.
            </p>
          </motion.div>
        </motion.section>

        {/* Recent builds */}
        <motion.section
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-40px' }}
          variants={stagger}
          className="mb-14"
        >
          <motion.h2 variants={fadeIn} className="text-xl font-semibold text-[var(--color-text-primary)] mb-4">
            Things I've Built So Far
          </motion.h2>
          <motion.p variants={fadeIn} className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
            This project is still evolving. Some of the pieces I've added recently:
          </motion.p>
          <div className="space-y-3">
            {recentBuilds.map((build) => (
              <motion.div
                key={build.title}
                variants={fadeIn}
                className="bg-[var(--color-bg-elevated)] rounded-[var(--radius-lg)] p-4 border border-[var(--color-border)]"
              >
                <h3 className="font-medium text-[var(--color-text-primary)] mb-0.5">
                  {build.title}
                </h3>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {build.detail}
                </p>
              </motion.div>
            ))}
          </div>
          <motion.p variants={fadeIn} className="text-[var(--color-text-muted)] text-sm mt-4">
            More experiments are ongoing.
          </motion.p>
        </motion.section>

        {/* Where this is going */}
        <motion.section
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-40px' }}
          variants={stagger}
          className="mb-14"
        >
          <motion.h2 variants={fadeIn} className="text-xl font-semibold text-[var(--color-text-primary)] mb-4">
            Where This Is Going
          </motion.h2>
          <motion.div variants={fadeIn}>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              Right now, Alfred is focused on cooking and meal planning.
            </p>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-4">
              Longer term, it's also a way for me to explore what a personal assistant looks like
              when it's built around real data and real tasks instead of isolated conversations.
              Not just limited to cooking, but other aspects of my life too. There are more
              efficient solutions out there, but this is just a hobby.
            </p>
            <p className="text-[var(--color-text-primary)] leading-relaxed font-medium">
              For now, it's just a tool I use and keep improving.
            </p>
          </motion.div>
        </motion.section>

        {/* CTA */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2 }}
          className="text-center pb-8"
        >
          <div className="bg-[var(--color-accent-muted)] rounded-[var(--radius-xl)] p-8 border border-[var(--color-border-accent)]">
            <p className="text-[var(--color-text-secondary)] mb-5">
              Want to try it out?
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-2 px-6 py-2.5 bg-[var(--color-accent)] text-white font-medium rounded-[var(--radius-md)] hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              Start Chatting
            </Link>
          </div>
        </motion.section>
      </div>
    </div>
  )
}
