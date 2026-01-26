import { useState, useRef, useEffect, FormEvent, Dispatch, SetStateAction } from 'react'
import { MessageBubble, Message } from './MessageBubble'
import { ChatInput } from './ChatInput'
import {
  StreamingProgress,
  createInitialPhaseState,
  updatePhaseState,
} from './StreamingProgress'
import { Mode } from '../../App'
import { apiStream } from '../../lib/api'
import { useChatContext } from '../../context/ChatContext'
import type { ActiveContext } from '../../types/chat'

interface ChatViewProps {
  messages: Message[]
  setMessages: Dispatch<SetStateAction<Message[]>>
  onOpenFocus: (item: { type: string; id: string }) => void
  mode: Mode
}

export function ChatView({ messages, setMessages, onOpenFocus, mode }: ChatViewProps) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  // V10: Phase-based progress tracking
  const [phaseState, setPhaseState] = useState(createInitialPhaseState())
  // V10: Active context state - can be used in future for persistent context bar
  const [, setActiveContext] = useState<ActiveContext | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { getAndClearUIChanges } = useChatContext()

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, phaseState])

  const handleSend = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!input.trim() || loading) return

    const userMessage = input.trim()
    setInput('')
    setLoading(true)
    // Reset phase state for new request
    setPhaseState(createInitialPhaseState())

    // Add user message
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: userMessage,
    }
    setMessages((prev) => [...prev, userMsg])

    try {
      // Get and clear UI changes to include with this message
      const uiChanges = getAndClearUIChanges()

      const res = await apiStream('/api/chat/stream', {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage,
          log_prompts: true,
          mode: mode, // V3: Pass mode to backend
          ui_changes: uiChanges.length > 0 ? uiChanges : undefined,
        }),
      })

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = 'progress'
      let latestActiveContext: ActiveContext | null = null
      // Track phase state locally to avoid React state timing issues
      let localPhaseState = createInitialPhaseState()

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
                // Update active context if included in done event
                if (data.active_context) {
                  latestActiveContext = data.active_context
                  setActiveContext(latestActiveContext)
                }
                // Final response - use latestActiveContext (local var) to avoid stale state
                const assistantMsg: Message = {
                  id: Date.now().toString(),
                  role: 'assistant',
                  content: data.response,
                  activeContext: latestActiveContext || undefined,
                }
                setMessages((prev) => [...prev, assistantMsg])
                setPhaseState(createInitialPhaseState())
              } else if (currentEvent === 'error') {
                throw new Error(data.error)
              } else {
                // V10: Handle all events through phase state machine
                const eventData = {
                  type: data.type || currentEvent,
                  ...data,
                }

                // Update active context tracking
                if (eventData.type === 'active_context') {
                  latestActiveContext = data.data || data
                  setActiveContext(latestActiveContext)
                }

                // Update phase state
                localPhaseState = updatePhaseState(localPhaseState, eventData)
                setPhaseState(localPhaseState)
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
      setPhaseState(createInitialPhaseState())
    } finally {
      setLoading(false)
    }
  }

  // Determine if we should show progress (has any activity)
  const hasProgress = phaseState.understand.context ||
    phaseState.think.complete ||
    phaseState.steps.length > 0

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

          {/* V10: Inline streaming progress */}
          {loading && hasProgress && (
            <div className="py-2">
              <StreamingProgress
                phase={phaseState}
                mode={mode === 'quick' ? 'quick' : 'plan'}
              />
            </div>
          )}

          {/* Initial loading state before any events */}
          {loading && !hasProgress && (
            <div className="py-2">
              <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4">
                <div className="flex items-center gap-2 text-sm text-[var(--color-accent)]">
                  <span className="w-4 text-center">●</span>
                  <span>{mode === 'quick' ? 'Working...' : 'Understanding...'}</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input - Fixed at bottom */}
      <div className="bg-[var(--color-bg-primary)] px-4 py-3 flex-shrink-0">
        <div className="max-w-2xl mx-auto">
          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={handleSend}
            disabled={loading}
            placeholder="Ask Alfred anything..."
          />
        </div>
      </div>
    </div>
  )
}
