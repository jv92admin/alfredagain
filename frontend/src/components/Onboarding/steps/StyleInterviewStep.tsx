import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../../lib/api'

interface StyleInterviewStepProps {
  onNext: () => void
  onBack: () => void
}

interface InterviewQuestion {
  id: string
  question: string
  hint: string
}

interface InterviewPage {
  page_number: number
  title: string
  subtitle: string
  questions: InterviewQuestion[]
  is_catchall: boolean
  ready_to_proceed?: boolean
}

interface Answer {
  question_id: string
  question: string
  answer: string
}

export function StyleInterviewStep({ onNext, onBack }: StyleInterviewStepProps) {
  const [currentPage, setCurrentPage] = useState(1)
  const [pageData, setPageData] = useState<InterviewPage | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [, setAllAnswers] = useState<Answer[]>([]) // Track all answers across pages
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [synthesizing, setSynthesizing] = useState(false)
  const [error, setError] = useState('')

  // Load interview page
  useEffect(() => {
    loadPage(currentPage)
  }, [currentPage])

  const loadPage = async (pageNum: number) => {
    setLoading(true)
    setError('')
    setAnswers({}) // Clear answers for new page

    try {
      const data = await apiRequest<InterviewPage>(`/api/onboarding/interview/page/${pageNum}`)
      setPageData(data)

      // Pre-fill with hints as placeholders (user can edit or clear)
      const initialAnswers: Record<string, string> = {}
      data.questions.forEach(q => {
        initialAnswers[q.id] = '' // Start empty, hint shown as placeholder
      })
      setAnswers(initialAnswers)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load questions')
    } finally {
      setLoading(false)
    }
  }

  const handleAnswerChange = (questionId: string, value: string) => {
    setAnswers(prev => ({ ...prev, [questionId]: value }))
  }

  const handleSubmitPage = async () => {
    if (!pageData) return

    // Validate at least some answers provided
    const answeredQuestions = pageData.questions.filter(q => answers[q.id]?.trim())
    if (answeredQuestions.length === 0 && pageData.questions.length > 0) {
      setError('Please answer at least one question')
      return
    }

    setSubmitting(true)
    setError('')

    try {
      // Format answers for API
      const pageAnswers: Answer[] = pageData.questions
        .filter(q => answers[q.id]?.trim())
        .map(q => ({
          question_id: q.id,
          question: q.question,
          answer: answers[q.id].trim(),
        }))

      // Submit to API
      const response = await apiRequest<{ success: boolean; next_page: number | null; ready_for_synthesis?: boolean }>(
        `/api/onboarding/interview/page/${currentPage}`,
        {
          method: 'POST',
          body: JSON.stringify({
            page_number: currentPage,
            answers: pageAnswers,
          }),
        }
      )

      // Store answers locally for display
      setAllAnswers(prev => [...prev, ...pageAnswers])

      if (response.ready_for_synthesis) {
        // All pages done, synthesize
        await handleSynthesize()
      } else if (response.next_page) {
        // Move to next page
        setCurrentPage(response.next_page)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save answers')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSynthesize = async () => {
    setSynthesizing(true)
    setError('')

    try {
      const response = await apiRequest<{ success: boolean; subdomain_guidance: Record<string, string> }>(
        '/api/onboarding/interview/synthesize',
        { method: 'POST' }
      )

      if (response.success) {
        // Move to next step in onboarding
        onNext()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to synthesize preferences')
      setSynthesizing(false)
    }
  }

  const handleSkipPage = async () => {
    // Allow skipping with empty answers
    setSubmitting(true)
    try {
      const response = await apiRequest<{ success: boolean; next_page: number | null; ready_for_synthesis?: boolean }>(
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

  const canGoBack = currentPage > 1

  // Loading state
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="w-8 h-8 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-[var(--color-text-muted)]">
          {currentPage === 1 ? 'Preparing your interview...' : 'Loading next questions...'}
        </p>
      </div>
    )
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

  if (!pageData) {
    return (
      <div className="text-center py-12">
        <p className="text-[var(--color-error)]">Failed to load interview</p>
        <button
          onClick={() => loadPage(currentPage)}
          className="mt-4 px-4 py-2 text-[var(--color-accent)] hover:underline"
        >
          Try again
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide">
            {pageData.is_catchall ? 'Final Questions' : `Part ${currentPage} of 4`}
          </span>
        </div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          {pageData.title}
        </h2>
        <p className="text-[var(--color-text-muted)]">
          {pageData.subtitle}
        </p>
      </div>

      {error && (
        <div className="p-3 bg-[var(--color-error-muted)] border border-[var(--color-error)] rounded-[var(--radius-md)] text-[var(--color-error)] text-sm">
          {error}
        </div>
      )}

      {/* Questions */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentPage}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
          className="space-y-6"
        >
          {pageData.questions.length === 0 && pageData.is_catchall && pageData.ready_to_proceed ? (
            // No follow-up questions needed
            <div className="text-center py-8">
              <div className="text-4xl mb-4">✨</div>
              <p className="text-[var(--color-text-primary)] font-medium">
                Great! I have everything I need.
              </p>
              <p className="text-[var(--color-text-muted)] mt-2">
                Let me create your personalized cooking profile...
              </p>
            </div>
          ) : (
            pageData.questions.map((question) => (
              <div key={question.id} className="space-y-2">
                <label className="block">
                  <span className="text-[var(--color-text-primary)] font-medium">
                    {question.question}
                  </span>
                </label>
                <textarea
                  value={answers[question.id] || ''}
                  onChange={(e) => handleAnswerChange(question.id, e.target.value)}
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
            ))
          )}
        </motion.div>
      </AnimatePresence>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-[var(--color-border-subtle)]">
        <div className="flex gap-2">
          {canGoBack && (
            <button
              onClick={() => setCurrentPage(currentPage - 1)}
              disabled={submitting}
              className="px-4 py-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors disabled:opacity-50"
            >
              ← Back
            </button>
          )}
          {!canGoBack && (
            <button
              onClick={onBack}
              disabled={submitting}
              className="px-4 py-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors disabled:opacity-50"
            >
              ← Back
            </button>
          )}
        </div>

        <div className="flex gap-3">
          {pageData.questions.length > 0 && (
            <button
              onClick={handleSkipPage}
              disabled={submitting}
              className="px-4 py-2 text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors disabled:opacity-50 text-sm"
            >
              Skip this section
            </button>
          )}
          
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={pageData.questions.length === 0 && pageData.ready_to_proceed ? handleSynthesize : handleSubmitPage}
            disabled={submitting}
            className="
              px-8 py-3 
              bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] 
              text-[var(--color-text-inverse)] 
              font-semibold 
              rounded-[var(--radius-lg)] 
              transition-colors 
              disabled:opacity-50
            "
          >
            {submitting ? 'Saving...' : 
             pageData.questions.length === 0 && pageData.ready_to_proceed ? 'Create My Profile' :
             currentPage === 4 ? 'Finish Interview' : 'Continue'}
          </motion.button>
        </div>
      </div>

      {/* Progress indicator for interview */}
      <div className="flex justify-center gap-2 pt-4">
        {[1, 2, 3, 4].map(page => (
          <div
            key={page}
            className={`
              w-2 h-2 rounded-full transition-colors
              ${page === currentPage 
                ? 'bg-[var(--color-accent)]' 
                : page < currentPage 
                  ? 'bg-[var(--color-accent-muted)]'
                  : 'bg-[var(--color-border)]'
              }
            `}
          />
        ))}
      </div>
    </div>
  )
}
