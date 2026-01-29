import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { AppShell } from './components/Layout/AppShell'
import { LoginPage } from './components/Auth/LoginPage'
import { ChatView } from './components/Chat/ChatView'
import { Message } from './components/Chat/MessageBubble'
import { RecipesView } from './components/Views/RecipesView'
import { MealPlanView } from './components/Views/MealPlanView'
import { InventoryView } from './components/Views/InventoryView'
import { ShoppingView } from './components/Views/ShoppingView'
import { TasksView } from './components/Views/TasksView'
import { IngredientsView } from './components/Views/IngredientsView'
import { PreferencesView } from './components/Views/PreferencesView'
import { FocusOverlay } from './components/Focus/FocusOverlay'
import { OnboardingFlow } from './components/Onboarding/OnboardingFlow'
import { ResumePrompt } from './components/Chat/ResumePrompt'
import { useAuth } from './hooks/useAuth'
import { apiRequest, pollJob } from './lib/api'
import { SessionStatusResponse } from './types/session'

// V3 Mode types
export type Mode = 'quick' | 'plan'

const INITIAL_MESSAGE: Message = {
  id: '1',
  role: 'assistant',
  content: "Hello! I'm Alfred, your kitchen assistant. I can help you manage your pantry, find recipes, create shopping lists, and plan meals. What would you like to do?",
}

function App() {
  const { user, loading, checkAuth } = useAuth()
  const [focusItem, setFocusItem] = useState<{ type: string; id: string } | null>(null)
  const [chatMessages, setChatMessages] = useState<Message[]>([INITIAL_MESSAGE])
  const mode: Mode = 'plan' // Default to plan mode (toggle removed)
  const [needsOnboarding, setNeedsOnboarding] = useState<boolean | null>(null)
  const onboardingCheckedForUser = useRef<string | null>(null)
  const [sessionStatus, setSessionStatus] = useState<SessionStatusResponse | null>(null)
  const [showResumePrompt, setShowResumePrompt] = useState(false)
  const sessionCheckedForUser = useRef<string | null>(null)
  const [, setActiveJobId] = useState<string | null>(null)
  const [jobLoading, setJobLoading] = useState(false)

  useEffect(() => {
    checkAuth()
  }, [])

  // Check if user needs onboarding after auth (only once per user)
  useEffect(() => {
    if (user && onboardingCheckedForUser.current !== user.user_id) {
      onboardingCheckedForUser.current = user.user_id
      checkOnboarding()
    }
  }, [user])

  const checkOnboarding = async () => {
    try {
      const state = await apiRequest<{ phase: string }>('/api/onboarding/state')
      // User needs onboarding if they haven't completed it
      // Backend returns lowercase phase values (e.g., "complete", "constraints")
      setNeedsOnboarding(state.phase !== 'complete')
    } catch (error) {
      // If API fails for a new user, show onboarding to be safe
      console.error('Onboarding check failed:', error)
      setNeedsOnboarding(true)
    }
  }

  const handleOnboardingComplete = () => {
    setNeedsOnboarding(false)
  }

  // Load conversation history and check session status after auth and onboarding
  useEffect(() => {
    if (user && needsOnboarding === false && sessionCheckedForUser.current !== user.user_id) {
      sessionCheckedForUser.current = user.user_id
      loadConversation()
    }
  }, [user, needsOnboarding])

  const loadConversation = async () => {
    try {
      const data = await apiRequest<SessionStatusResponse>('/api/conversation/status')
      setSessionStatus(data)

      // 1. Load message history from recent_turns
      if (data.messages && data.messages.length > 0) {
        setChatMessages([INITIAL_MESSAGE, ...data.messages])
      }

      // 2. Handle session status (resume prompt)
      if (data.status === 'stale') {
        setShowResumePrompt(true)
      }

      // 3. Handle active job
      if (data.active_job?.status === 'running') {
        setJobLoading(true)
        const finished = await pollJob(data.active_job.id)
        if (finished.status === 'complete' && finished.output) {
          setChatMessages(prev => [...prev, {
            id: `a-${finished.id}`,
            role: 'assistant' as const,
            content: finished.output.response,
          }])
          await apiRequest(`/api/jobs/${finished.id}/ack`, { method: 'POST' })
        }
        setJobLoading(false)
      } else if (data.active_job?.status === 'complete') {
        // Job complete but unacked — messages already in history, just ack
        await apiRequest(`/api/jobs/${data.active_job.id}/ack`, { method: 'POST' })
      }
    } catch (error) {
      console.error('Failed to load conversation:', error)
    }
  }

  const handleResumeSession = () => {
    // Implicit resume - just dismiss the prompt, backend context preserved
    setShowResumePrompt(false)
  }

  const handleStartFresh = async () => {
    try {
      await apiRequest('/api/chat/reset', { method: 'POST' })
    } catch (error) {
      console.error('Failed to reset session:', error)
    }
    setChatMessages([INITIAL_MESSAGE])
    setShowResumePrompt(false)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--color-bg-primary)]">
        <div className="text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    )
  }

  if (!user) {
    return <LoginPage onLogin={checkAuth} />
  }

  // Show onboarding if needed (still checking = null, needs = true)
  if (needsOnboarding === null) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--color-bg-primary)]">
        <div className="text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    )
  }

  if (needsOnboarding) {
    return <OnboardingFlow onComplete={handleOnboardingComplete} />
  }

  const handleNewChat = async () => {
    try {
      await apiRequest('/api/chat/reset', { method: 'POST' })
    } catch (error) {
      console.error('Failed to reset backend session:', error)
      // Still clear UI even if backend fails
    }
    setChatMessages([INITIAL_MESSAGE])
  }

  return (
    <>
      <AppShell user={user} onNewChat={handleNewChat}>
        <Routes>
          <Route path="/" element={<ChatView messages={chatMessages} setMessages={setChatMessages} onOpenFocus={setFocusItem} mode={mode} setActiveJobId={setActiveJobId} jobLoading={jobLoading} setJobLoading={setJobLoading} />} />
          <Route path="/recipes" element={<RecipesView onOpenFocus={setFocusItem} />} />
          <Route path="/meals" element={<MealPlanView onOpenFocus={setFocusItem} />} />
          <Route path="/inventory" element={<InventoryView />} />
          <Route path="/shopping" element={<ShoppingView />} />
          <Route path="/tasks" element={<TasksView />} />
          <Route path="/ingredients" element={<IngredientsView />} />
          <Route path="/preferences" element={<PreferencesView />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>

      {focusItem && (
        <FocusOverlay
          type={focusItem.type}
          id={focusItem.id}
          onClose={() => setFocusItem(null)}
        />
      )}

      {showResumePrompt && sessionStatus && (
        <ResumePrompt
          sessionStatus={sessionStatus}
          onResume={handleResumeSession}
          onStartFresh={handleStartFresh}
        />
      )}
    </>
  )
}

export default App
