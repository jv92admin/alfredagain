import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../../lib/api'
import { ChipQuestion } from './ChipQuestion'
import { InterviewPageLayout } from './InterviewPageLayout'

interface StyleInterviewStepProps {
  onNext: () => void
  onBack: () => void
}

// =============================================================================
// Types
// =============================================================================

interface ChipOption {
  label: string
  value: string
}

interface ChipQuestionDef {
  id: string
  type: 'chips'
  multi?: boolean
  question: string
  options: ChipOption[]
}

interface TextQuestionDef {
  id: string
  type: 'text'
  question: string
  hint: string
}

type QuestionDef = ChipQuestionDef | TextQuestionDef

interface StaticPageDef {
  page_number: number
  title: string
  subtitle: string
  image: string
  questions: QuestionDef[]
  is_catchall: false
}

interface CatchallQuestion {
  id: string
  question: string
  hint: string
}

interface CatchallPageDef {
  page_number: number
  title: string
  subtitle: string
  questions: CatchallQuestion[]
  is_catchall: true
  ready_to_proceed?: boolean
}

// =============================================================================
// Static Page Definitions (mirrors backend STATIC_PAGES)
// =============================================================================

const STATIC_PAGES: StaticPageDef[] = [
  {
    page_number: 1,
    title: 'Recipes & Cooking Style',
    subtitle: 'Alfred writes and catalogs recipes tailored to how you actually cook — from quick weeknight dinners to weekend projects.',
    image: '/onboarding/onboarding-recipes.svg',
    is_catchall: false,
    questions: [
      {
        id: 'recipe_competence',
        type: 'chips',
        multi: false,
        question: 'How much should Alfred assume you know?',
        options: [
          { label: 'Assume I know the basics', value: 'assume_basics' },
          { label: 'Explain key techniques', value: 'explain_techniques' },
          { label: 'Walk me through everything', value: 'walk_through' },
        ],
      },
      {
        id: 'timing_preference',
        type: 'chips',
        multi: false,
        question: 'How do you prefer timing info?',
        options: [
          { label: 'Visual cues & intuition', value: 'visual_cues' },
          { label: 'Times + visual cues', value: 'times_and_cues' },
          { label: 'Exact temps & times', value: 'exact_times' },
        ],
      },
      {
        id: 'weeknight_time',
        type: 'chips',
        multi: false,
        question: 'How much time do you usually have for weeknight cooking?',
        options: [
          { label: 'Under 20 min', value: 'under_20' },
          { label: '20-40 min', value: '20_to_40' },
          { label: '40-60 min', value: '40_to_60' },
          { label: 'No rush', value: 'no_rush' },
        ],
      },
      {
        id: 'recipe_extras',
        type: 'chips',
        multi: true,
        question: 'What extras are useful to you?',
        options: [
          { label: "Substitutions when I'm missing something", value: 'substitutions' },
          { label: 'Chef tips & "why" behind techniques', value: 'chef_tips' },
          { label: 'Troubleshooting if something goes wrong', value: 'troubleshooting' },
        ],
      },
      {
        id: 'cooking_style',
        type: 'text',
        question: "What kind of cooking makes you happy? Comfort food, healthy experiments, impressing guests, quick fuel — what's your vibe?",
        hint: "Weeknights are comfort food — pasta, stir fry, one-pot stuff. Weekends I like trying something new",
      },
    ],
  },
  {
    page_number: 2,
    title: 'Shopping & Ingredients',
    subtitle: "Alfred maintains your shopping lists and tracks what's in your pantry — so you always know what you have and what you need.",
    image: '/onboarding/onboarding-pantry.svg',
    is_catchall: false,
    questions: [
      {
        id: 'shopping_detail',
        type: 'chips',
        multi: false,
        question: 'What helps you shop fastest?',
        options: [
          { label: 'Quick scan — items, rough amounts', value: 'quick_scan' },
          { label: 'Full detail — exact quantities, notes', value: 'full_detail' },
        ],
      },
      {
        id: 'shopping_frequency',
        type: 'chips',
        multi: false,
        question: 'How do you typically shop?',
        options: [
          { label: 'One big weekly trip', value: 'weekly_trip' },
          { label: 'Multiple small trips', value: 'small_trips' },
          { label: 'Online delivery', value: 'online' },
          { label: 'Mix of stores', value: 'mix_stores' },
        ],
      },
      {
        id: 'shopping_organization',
        type: 'chips',
        multi: false,
        question: 'How should Alfred organize your lists?',
        options: [
          { label: 'By recipe — "for the curry: ..."', value: 'by_recipe' },
          { label: 'By store section — Produce, Dairy, Meat', value: 'by_section' },
        ],
      },
      {
        id: 'grocery_frustration',
        type: 'text',
        question: "What usually goes wrong with groceries? Produce going bad, missing ingredients mid-cook, no good stores nearby?",
        hint: "I buy fresh herbs for one recipe and the rest goes bad. Also my store doesn't carry half the stuff recipes call for",
      },
    ],
  },
  {
    page_number: 3,
    title: 'Meal Planning & Prep',
    subtitle: "Alfred plans your meals and sends prep reminders — so nothing catches you off guard on a busy Tuesday.",
    image: '/onboarding/onboarding-mealplan.svg',
    is_catchall: false,
    questions: [
      {
        id: 'cooking_rhythm',
        type: 'chips',
        multi: false,
        question: "What's your cooking rhythm?",
        options: [
          { label: 'Cook fresh each day', value: 'fresh_daily' },
          { label: 'Mix of fresh and batch', value: 'mixed' },
          { label: 'Weekend batch + weekday assembly', value: 'batch_assembly' },
        ],
      },
      {
        id: 'leftover_strategy',
        type: 'chips',
        multi: false,
        question: 'How do you handle leftovers?',
        options: [
          { label: 'Happy eating the same thing', value: 'same_meal' },
          { label: 'Transform into new dishes', value: 'transform' },
          { label: 'Leftovers lose quality, prefer fresh', value: 'prefer_fresh' },
        ],
      },
      {
        id: 'prep_reminder_detail',
        type: 'chips',
        multi: false,
        question: 'How much context do you want in prep reminders?',
        options: [
          { label: 'Just the task — "thaw chicken"', value: 'task_only' },
          { label: 'Include the meal — "thaw chicken for Thursday\'s stir-fry"', value: 'with_meal' },
          { label: 'Full scheduling — "thaw 1.5lb chicken (Thursday stir-fry), move to fridge by Tue 6pm"', value: 'full_context' },
        ],
      },
      {
        id: 'ideal_week',
        type: 'text',
        question: "Do you like long weekend cooks? What do weekdays look like? How often are you actually cooking?",
        hint: "We cook maybe 4-5 nights. Weeknights are quick — 30 min max. Weekends I'll do something involved if I'm in the mood",
      },
    ],
  },
]

const TOTAL_PAGES = 4 // 3 static + 1 catchall

// =============================================================================
// Answer State Types
// =============================================================================

interface ChipAnswer {
  question_id: string
  type: 'chips'
  value?: string
  values?: string[]
}

interface TextAnswer {
  question_id: string
  type: 'text'
  answer: string
}

type Answer = ChipAnswer | TextAnswer

// =============================================================================
// Component
// =============================================================================

export function StyleInterviewStep({ onNext, onBack }: StyleInterviewStepProps) {
  const [currentPage, setCurrentPage] = useState(1)
  const [catchallData, setCatchallData] = useState<CatchallPageDef | null>(null)
  const [loadingCatchall, setLoadingCatchall] = useState(false)

  // Per-page answers: pageNumber → answer map
  const [pageAnswers, setPageAnswers] = useState<Record<number, Record<string, Answer>>>({})
  const [submitting, setSubmitting] = useState(false)
  const [synthesizing, setSynthesizing] = useState(false)
  const [error, setError] = useState('')

  // Load catchall page when we reach page 4
  useEffect(() => {
    if (currentPage === 4 && !catchallData) {
      loadCatchallPage()
    }
  }, [currentPage])

  const loadCatchallPage = async () => {
    setLoadingCatchall(true)
    setError('')
    try {
      const data = await apiRequest<CatchallPageDef>('/api/onboarding/interview/page/4')
      setCatchallData(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load follow-up questions')
    } finally {
      setLoadingCatchall(false)
    }
  }

  // Get or initialize answers for the current page
  const getCurrentAnswers = (): Record<string, Answer> => {
    return pageAnswers[currentPage] || {}
  }

  const updateAnswer = (questionId: string, answer: Answer) => {
    setPageAnswers(prev => ({
      ...prev,
      [currentPage]: {
        ...(prev[currentPage] || {}),
        [questionId]: answer,
      },
    }))
  }

  const getChipValue = (questionId: string): string | null => {
    const ans = getCurrentAnswers()[questionId]
    if (ans?.type === 'chips' && ans.value) return ans.value
    return null
  }

  const getChipValues = (questionId: string): string[] => {
    const ans = getCurrentAnswers()[questionId]
    if (ans?.type === 'chips' && ans.values) return ans.values
    return []
  }

  const getTextValue = (questionId: string): string => {
    const ans = getCurrentAnswers()[questionId]
    if (ans?.type === 'text') return ans.answer
    return ''
  }

  // Collect all answers across pages for submission
  const collectPageAnswers = (pageNum: number): Answer[] => {
    const answers = pageAnswers[pageNum] || {}
    return Object.values(answers).filter(ans => {
      if (ans.type === 'chips') {
        return ans.value || (ans.values && ans.values.length > 0)
      }
      if (ans.type === 'text') {
        return ans.answer?.trim()
      }
      return false
    })
  }

  const handleSubmitPage = async () => {
    setSubmitting(true)
    setError('')

    try {
      const answers = collectPageAnswers(currentPage)

      const response = await apiRequest<{
        success: boolean
        next_page: number | null
        ready_for_synthesis?: boolean
      }>(
        `/api/onboarding/interview/page/${currentPage}`,
        {
          method: 'POST',
          body: JSON.stringify({
            page_number: currentPage,
            answers,
          }),
        }
      )

      if (response.ready_for_synthesis) {
        await handleSynthesize()
      } else if (response.next_page) {
        setCurrentPage(response.next_page)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save answers')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSkipPage = async () => {
    setSubmitting(true)
    setError('')
    try {
      const response = await apiRequest<{
        success: boolean
        next_page: number | null
        ready_for_synthesis?: boolean
      }>(
        `/api/onboarding/interview/page/${currentPage}`,
        {
          method: 'POST',
          body: JSON.stringify({
            page_number: currentPage,
            answers: [],
          }),
        }
      )

      if (response.ready_for_synthesis) {
        await handleSynthesize()
      } else if (response.next_page) {
        setCurrentPage(response.next_page)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to skip')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSynthesize = async () => {
    setSynthesizing(true)
    setError('')

    try {
      const response = await apiRequest<{
        success: boolean
        subdomain_guidance: Record<string, string>
      }>(
        '/api/onboarding/interview/synthesize',
        { method: 'POST' }
      )

      if (response.success) {
        onNext()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to synthesize preferences')
      setSynthesizing(false)
    }
  }

  const handleBack = () => {
    if (currentPage > 1) {
      setCurrentPage(currentPage - 1)
    } else {
      onBack()
    }
  }

  // Synthesizing state
  if (synthesizing) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="w-8 h-8 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-[var(--color-text-muted)]">
          Analyzing your preferences...
        </p>
        <p className="text-[var(--color-text-muted)] text-sm mt-2">
          Creating your personalized cooking profile
        </p>
      </div>
    )
  }

  // =============================================================================
  // Static Pages (1-3)
  // =============================================================================

  if (currentPage <= 3) {
    const pageDef = STATIC_PAGES[currentPage - 1]

    return (
      <AnimatePresence mode="wait">
        <motion.div
          key={currentPage}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.2 }}
        >
          <InterviewPageLayout
            pageNumber={currentPage}
            totalPages={TOTAL_PAGES}
            title={pageDef.title}
            subtitle={pageDef.subtitle}
            image={pageDef.image}
            onBack={handleBack}
            onSkip={handleSkipPage}
            onSubmit={handleSubmitPage}
            submitLabel={currentPage === 3 ? 'Continue' : 'Continue'}
            submitting={submitting}
            error={error}
          >
            {pageDef.questions.map((q) => {
              if (q.type === 'chips') {
                const chipQ = q as ChipQuestionDef
                return (
                  <ChipQuestion
                    key={q.id}
                    question={chipQ.question}
                    options={chipQ.options}
                    multi={chipQ.multi}
                    value={getChipValue(q.id)}
                    values={getChipValues(q.id)}
                    onChange={(value, values) => {
                      if (chipQ.multi) {
                        updateAnswer(q.id, { question_id: q.id, type: 'chips', values })
                      } else {
                        updateAnswer(q.id, { question_id: q.id, type: 'chips', value: value ?? undefined })
                      }
                    }}
                  />
                )
              }

              if (q.type === 'text') {
                const textQ = q as TextQuestionDef
                return (
                  <div key={q.id} className="space-y-2">
                    <label className="block text-[var(--color-text-primary)] font-medium">
                      {textQ.question}
                    </label>
                    <textarea
                      value={getTextValue(q.id)}
                      onChange={(e) =>
                        updateAnswer(q.id, {
                          question_id: q.id,
                          type: 'text',
                          answer: e.target.value,
                        })
                      }
                      placeholder={textQ.hint}
                      rows={3}
                      className="
                        w-full px-4 py-3
                        bg-[var(--color-bg-secondary)]
                        border border-[var(--color-border)]
                        rounded-[var(--radius-lg)]
                        text-[var(--color-text-primary)]
                        placeholder:text-[var(--color-text-muted)]
                        placeholder:italic
                        focus:outline-none focus:border-[var(--color-accent)]
                        transition-colors
                        resize-none
                      "
                    />
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Write in your own words — the example is just a guide
                    </p>
                  </div>
                )
              }

              return null
            })}
          </InterviewPageLayout>
        </motion.div>
      </AnimatePresence>
    )
  }

  // =============================================================================
  // Page 4: LLM Catchall
  // =============================================================================

  if (loadingCatchall) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="w-8 h-8 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-[var(--color-text-muted)]">
          Reviewing your answers for any follow-ups...
        </p>
      </div>
    )
  }

  if (!catchallData) {
    return (
      <div className="text-center py-12">
        <p className="text-[var(--color-error)]">Failed to load follow-up questions</p>
        <button
          onClick={loadCatchallPage}
          className="mt-4 px-4 py-2 text-[var(--color-accent)] hover:underline"
        >
          Try again
        </button>
      </div>
    )
  }

  // If catchall says ready_to_proceed and no questions, auto-synthesize
  if (catchallData.ready_to_proceed && catchallData.questions.length === 0) {
    return (
      <InterviewPageLayout
        pageNumber={4}
        totalPages={TOTAL_PAGES}
        title="Almost Done"
        subtitle={catchallData.subtitle}
        onBack={handleBack}
        onSubmit={handleSynthesize}
        submitLabel="Create My Profile"
        submitting={synthesizing}
        error={error}
      >
        <div className="text-center py-8">
          <p className="text-[var(--color-text-primary)] font-medium">
            Great! I have everything I need.
          </p>
          <p className="text-[var(--color-text-muted)] mt-2">
            Let me create your personalized cooking profile...
          </p>
        </div>
      </InterviewPageLayout>
    )
  }

  // Catchall with follow-up questions
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key="catchall"
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -20 }}
        transition={{ duration: 0.2 }}
      >
        <InterviewPageLayout
          pageNumber={4}
          totalPages={TOTAL_PAGES}
          title="Almost Done"
          subtitle={catchallData.subtitle}
          onBack={handleBack}
          onSkip={handleSkipPage}
          onSubmit={handleSubmitPage}
          submitLabel="Finish Interview"
          submitting={submitting}
          error={error}
        >
          {catchallData.questions.map((question) => (
            <div key={question.id} className="space-y-2">
              <label className="block text-[var(--color-text-primary)] font-medium">
                {question.question}
              </label>
              <textarea
                value={getTextValue(question.id)}
                onChange={(e) =>
                  updateAnswer(question.id, {
                    question_id: question.id,
                    type: 'text',
                    answer: e.target.value,
                  })
                }
                placeholder={question.hint}
                rows={3}
                className="
                  w-full px-4 py-3
                  bg-[var(--color-bg-secondary)]
                  border border-[var(--color-border)]
                  rounded-[var(--radius-lg)]
                  text-[var(--color-text-primary)]
                  placeholder:text-[var(--color-text-muted)]
                  placeholder:italic
                  focus:outline-none focus:border-[var(--color-accent)]
                  transition-colors
                  resize-none
                "
              />
              <p className="text-xs text-[var(--color-text-muted)]">
                Write in your own words — the example is just a guide
              </p>
            </div>
          ))}
        </InterviewPageLayout>
      </motion.div>
    </AnimatePresence>
  )
}
