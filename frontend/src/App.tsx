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
import { useAuth } from './hooks/useAuth'
import { apiRequest } from './lib/api'

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

  const handleNewChat = () => {
    setChatMessages([INITIAL_MESSAGE])
  }

  return (
    <>
      <AppShell user={user} onNewChat={handleNewChat}>
        <Routes>
          <Route path="/" element={<ChatView messages={chatMessages} setMessages={setChatMessages} onOpenFocus={setFocusItem} mode={mode} />} />
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
    </>
  )
}

export default App
