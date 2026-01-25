import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

// Types for UI changes tracking
export interface UIChange {
  action: 'created:user' | 'updated:user' | 'deleted:user'
  entity_type: string
  id: string      // Always UUID
  label: string
  data?: Record<string, unknown>  // Fresh entity data for creates/updates
}

interface ChatContextValue {
  // UI changes tracking (cleared after sending with chat message)
  uiChanges: UIChange[]
  pushUIChange: (change: UIChange) => void
  clearUIChanges: () => void
  getAndClearUIChanges: () => UIChange[]
}

const ChatContext = createContext<ChatContextValue | null>(null)

interface ChatProviderProps {
  children: ReactNode
}

export function ChatProvider({ children }: ChatProviderProps) {
  const [uiChanges, setUIChanges] = useState<UIChange[]>([])

  const pushUIChange = useCallback((change: UIChange) => {
    setUIChanges(prev => [...prev, change])
  }, [])

  const clearUIChanges = useCallback(() => {
    setUIChanges([])
  }, [])

  // Get changes and clear in one operation (for sending with chat message)
  const getAndClearUIChanges = useCallback(() => {
    const changes = uiChanges
    setUIChanges([])
    return changes
  }, [uiChanges])

  return (
    <ChatContext.Provider value={{
      uiChanges,
      pushUIChange,
      clearUIChanges,
      getAndClearUIChanges,
    }}>
      {children}
    </ChatContext.Provider>
  )
}

export function useChatContext() {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChatContext must be used within a ChatProvider')
  }
  return context
}

// Convenience hook for Views that only need to push changes
export function useUIChanges() {
  const { pushUIChange } = useChatContext()
  return { pushUIChange }
}
