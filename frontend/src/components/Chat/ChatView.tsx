import { useState, useRef, useEffect, FormEvent, Dispatch, SetStateAction } from 'react'
import { MessageBubble, Message } from './MessageBubble'
import { ChatInput } from './ChatInput'
import { ProgressTrail, ProgressStep } from './ProgressTrail'
import { Mode } from '../../App'

interface ChatViewProps {
  messages: Message[]
  setMessages: Dispatch<SetStateAction<Message[]>>
  onOpenFocus: (item: { type: string; id: string }) => void
  mode: Mode
  onModeChange: (mode: Mode) => void
}

interface AffectedEntity {
  type: string
  id: string
  name: string
  action?: string
  state?: 'pending' | 'active' // V3 entity state
}

export function ChatView({ messages, setMessages, onOpenFocus, mode, onModeChange }: ChatViewProps) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState<ProgressStep[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, progress])

  const handleSend = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!input.trim() || loading) return

    const userMessage = input.trim()
    setInput('')
    setLoading(true)
    setProgress([{ label: mode === 'quick' ? 'Working...' : 'Planning...', status: 'active' }])

    // Add user message
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: userMessage,
    }
    setMessages((prev) => [...prev, userMsg])

    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: userMessage, 
          log_prompts: true,
          mode: mode, // V3: Pass mode to backend
        }),
        credentials: 'include',
      })

      if (!res.ok) throw new Error('Chat failed')

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = 'progress'
      const affectedEntities: AffectedEntity[] = []
      const steps: string[] = []

      while (reader) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              
              if (currentEvent === 'done') {
                // Final response
                const assistantMsg: Message = {
                  id: Date.now().toString(),
                  role: 'assistant',
                  content: data.response,
                  entities: affectedEntities,
                }
                setMessages((prev) => [...prev, assistantMsg])
                setProgress([])
              } else if (currentEvent === 'error') {
                throw new Error(data.error)
              } else if (data.type === 'plan') {
                // Got the plan
                steps.push(...(data.steps || []))
                setProgress(
                  steps.map((s, i) => ({
                    label: `Step ${i + 1}: ${s}`,
                    status: 'pending' as const,
                  }))
                )
              } else if (data.type === 'step') {
                // Step starting
                setProgress((prev) =>
                  prev.map((p, i) => ({
                    ...p,
                    status: i === data.step - 1 ? 'active' : i < data.step - 1 ? 'completed' : 'pending',
                  }))
                )
              } else if (data.type === 'step_complete') {
                // Collect affected entities with state
                // Skip child/junction tables - users don't need to see these as separate entities
                const SKIP_TABLES = ['recipe_ingredients']
                
                // Helper to extract a display name from a record
                const getEntityName = (table: string, record: Record<string, unknown>): string => {
                  // Use name/title if available
                  if (record.name) return record.name as string
                  if (record.title) return record.title as string
                  
                  // Special handling for meal_plans: "Jan 15 - Dinner"
                  if (table === 'meal_plans' && record.date && record.meal_type) {
                    const date = new Date(record.date as string)
                    const formatted = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                    const mealType = (record.meal_type as string).charAt(0).toUpperCase() + (record.meal_type as string).slice(1)
                    return `${formatted} - ${mealType}`
                  }
                  
                  // Special handling for tasks
                  if (table === 'tasks' && record.description) {
                    const desc = record.description as string
                    return desc.length > 30 ? desc.slice(0, 30) + '...' : desc
                  }
                  
                  // Fallback
                  return table.replace('_', ' ')
                }
                
                if (data.data) {
                  for (const [table, records] of Object.entries(data.data)) {
                    if (SKIP_TABLES.includes(table)) continue
                    
                    if (Array.isArray(records)) {
                      for (const record of records as Record<string, unknown>[]) {
                        if (record.id) {
                          affectedEntities.push({
                            type: table,
                            id: record.id as string,
                            name: getEntityName(table, record),
                            state: (record.state as 'pending' | 'active') || 'active',
                          })
                        }
                      }
                    }
                  }
                }
                // Mark step complete
                setProgress((prev) =>
                  prev.map((p, i) => ({
                    ...p,
                    status: i === data.step - 1 ? 'completed' : p.status,
                  }))
                )
              }
            } catch {
              // Ignore parse errors
            }
          }
        }
      }
    } catch (err) {
      const errorMsg: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Sorry, something went wrong: ${err instanceof Error ? err.message : 'Unknown error'}`,
      }
      setMessages((prev) => [...prev, errorMsg])
      setProgress([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-2xl mx-auto space-y-4">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onOpenFocus={onOpenFocus}
            />
          ))}

          {/* Progress indicator */}
          {loading && progress.length > 0 && (
            <div className="py-2">
              <ProgressTrail steps={progress} />
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input - Fixed at bottom */}
      <div className="border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4 flex-shrink-0">
        <div className="max-w-2xl mx-auto">
          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={handleSend}
            disabled={loading}
            placeholder={mode === 'quick' ? "Quick question..." : "Ask Alfred anything..."}
            mode={mode}
            onModeChange={onModeChange}
          />
        </div>
      </div>
    </div>
  )
}
