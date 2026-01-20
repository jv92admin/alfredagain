import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { ConstraintsStep } from './steps/ConstraintsStep'
import { PantryStep } from './steps/PantryStep'
import { CuisinesStep } from './steps/CuisinesStep'
import { DiscoveryStep } from './steps/DiscoveryStep'
import { StyleInterviewStep } from './steps/StyleInterviewStep'

interface OnboardingFlowProps {
  onComplete: () => void
}

type Step = 'constraints' | 'pantry' | 'cuisines' | 'discovery' | 'interview' | 'complete'

interface OnboardingState {
  phase: string
  constraints: any
  cuisine_preferences: string[]
  initial_inventory: any[]
  ingredient_preferences: { likes: number; dislikes: number }
}

// Note: pantry + discovery steps hidden until ingredient DB improvements
const STEPS: { id: Step; label: string }[] = [
  { id: 'constraints', label: 'Basics' },
  { id: 'cuisines', label: 'Cuisines' },
  { id: 'interview', label: 'Style' },
]

export function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const [currentStep, setCurrentStep] = useState<Step>('constraints')
  const [loading, setLoading] = useState(true)

  // Load current onboarding state on mount
  useEffect(() => {
    loadState()
  }, [])

  const loadState = async () => {
    try {
      const data = await apiRequest<OnboardingState>('/api/onboarding/state')
      
      // Resume from where user left off based on phase
      const phase = data.phase?.toUpperCase()
      
      if (phase === 'CONSTRAINTS') {
        setCurrentStep('constraints')
      } else if (phase === 'DISCOVERY') {
        // Skipping pantry/discovery for now - go to cuisines or interview
        if (!data.constraints) {
          setCurrentStep('constraints')
        } else if (data.cuisine_preferences.length === 0) {
          setCurrentStep('cuisines')
        } else {
          // Skip discovery, go straight to interview
          setCurrentStep('interview')
        }
      } else if (phase === 'STYLE_RECIPES' || phase === 'STYLE_MEAL_PLANS' || phase === 'STYLE_TASKS' || phase === 'HABITS') {
        // All style-related phases go to interview step
        setCurrentStep('interview')
      } else if (phase === 'PREVIEW') {
        // TODO: Add preview step later
        setCurrentStep('interview')
      } else if (phase === 'COMPLETE') {
        onComplete()
      } else {
        // Default to constraints if phase unknown
        setCurrentStep('constraints')
      }
    } catch (error) {
      console.error('Failed to load onboarding state:', error)
    } finally {
      setLoading(false)
    }
  }

  const nextStep = async () => {
    // Note: pantry + discovery steps hidden until ingredient DB improvements
    const stepOrder: Step[] = ['constraints', 'cuisines', 'interview', 'complete']
    const idx = stepOrder.indexOf(currentStep)
    if (idx < stepOrder.length - 1) {
      const next = stepOrder[idx + 1]
      if (next === 'complete') {
        // Call backend to finalize and apply preferences
        try {
          await apiRequest('/api/onboarding/complete', { method: 'POST' })
        } catch (error) {
          console.error('Failed to complete onboarding:', error)
          // Continue anyway - preferences might already be applied
        }
        onComplete()
      } else {
        setCurrentStep(next)
      }
    }
  }

  const prevStep = () => {
    // Note: pantry + discovery steps hidden until ingredient DB improvements
    const stepOrder: Step[] = ['constraints', 'cuisines', 'interview']
    const idx = stepOrder.indexOf(currentStep)
    if (idx > 0) {
      setCurrentStep(stepOrder[idx - 1])
    }
  }

  const currentStepIndex = STEPS.findIndex(s => s.id === currentStep)

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)]">
        <div className="text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg-primary)] flex flex-col">
      {/* Header */}
      <header className="p-6 border-b border-[var(--color-border)]">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <h1 className="text-2xl font-light tracking-[3px] text-[var(--color-accent)]">
            ALFRED
          </h1>
          <span className="text-[var(--color-text-muted)] text-sm">
            Let's get you set up
          </span>
        </div>
      </header>

      {/* Progress Bar */}
      <div className="p-6 border-b border-[var(--color-border-subtle)]">
        <div className="max-w-2xl mx-auto">
          <div className="flex items-center justify-between mb-2">
            {STEPS.map((step, idx) => (
              <div
                key={step.id}
                className="flex items-center"
              >
                <div
                  className={`
                    w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                    transition-colors duration-300
                    ${idx < currentStepIndex 
                      ? 'bg-[var(--color-accent)] text-[var(--color-text-inverse)]' 
                      : idx === currentStepIndex
                        ? 'bg-[var(--color-accent-muted)] text-[var(--color-accent)] border-2 border-[var(--color-accent)]'
                        : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]'
                    }
                  `}
                >
                  {idx < currentStepIndex ? '✓' : idx + 1}
                </div>
                {idx < STEPS.length - 1 && (
                  <div
                    className={`
                      w-16 sm:w-24 h-0.5 mx-2
                      transition-colors duration-300
                      ${idx < currentStepIndex 
                        ? 'bg-[var(--color-accent)]' 
                        : 'bg-[var(--color-border)]'
                      }
                    `}
                  />
                )}
              </div>
            ))}
          </div>
          <div className="flex justify-between text-xs text-[var(--color-text-muted)]">
            {STEPS.map((step, idx) => (
              <span
                key={step.id}
                className={idx === currentStepIndex ? 'text-[var(--color-accent)]' : ''}
              >
                {step.label}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Step Content */}
      <main className="flex-1 p-6 overflow-auto">
        <div className="max-w-2xl mx-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentStep}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              {currentStep === 'constraints' && (
                <ConstraintsStep onNext={nextStep} />
              )}
              {currentStep === 'pantry' && (
                <PantryStep onNext={nextStep} onBack={prevStep} />
              )}
              {currentStep === 'cuisines' && (
                <CuisinesStep onNext={nextStep} onBack={prevStep} />
              )}
              {currentStep === 'discovery' && (
                <DiscoveryStep onNext={nextStep} onBack={prevStep} />
              )}
              {currentStep === 'interview' && (
                <StyleInterviewStep onNext={nextStep} onBack={prevStep} />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  )
}
