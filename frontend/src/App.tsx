import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { AppShell } from './components/Layout/AppShell'
import { LoginPage } from './components/Auth/LoginPage'
import { ChatView } from './components/Chat/ChatView'
import { Message } from './components/Chat/MessageBubble'
import { RecipesView } from './components/Views/RecipesView'
import { MealPlanView } from './components/Views/MealPlanView'
import { InventoryView } from './components/Views/InventoryView'
import { ShoppingView } from './components/Views/ShoppingView'
import { TasksView } from './components/Views/TasksView'
import { FocusOverlay } from './components/Focus/FocusOverlay'
import { useAuth } from './hooks/useAuth'

const INITIAL_MESSAGE: Message = {
  id: '1',
  role: 'assistant',
  content: "Hello! I'm Alfred, your kitchen assistant. I can help you manage your pantry, find recipes, create shopping lists, and plan meals. What would you like to do?",
}

function App() {
  const { user, loading, checkAuth } = useAuth()
  const [focusItem, setFocusItem] = useState<{ type: string; id: string } | null>(null)
  const [chatMessages, setChatMessages] = useState<Message[]>([INITIAL_MESSAGE])

  useEffect(() => {
    checkAuth()
  }, [])

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

  const handleNewChat = () => {
    setChatMessages([INITIAL_MESSAGE])
  }

  return (
    <>
      <AppShell user={user} onNewChat={handleNewChat}>
        <Routes>
          <Route path="/" element={<ChatView messages={chatMessages} setMessages={setChatMessages} onOpenFocus={setFocusItem} />} />
          <Route path="/recipes" element={<RecipesView onOpenFocus={setFocusItem} />} />
          <Route path="/meals" element={<MealPlanView onOpenFocus={setFocusItem} />} />
          <Route path="/inventory" element={<InventoryView />} />
          <Route path="/shopping" element={<ShoppingView />} />
          <Route path="/tasks" element={<TasksView />} />
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

