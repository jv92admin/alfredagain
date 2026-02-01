import { useState, useRef, useEffect, FormEvent, Dispatch, SetStateAction } from 'react'
import { MessageBubble, Message } from './MessageBubble'
import { ChatInput } from './ChatInput'
import {
  StreamingProgress,
  createInitialPhaseState,
  updatePhaseState,
} from './StreamingProgress'
import { ThinkingIndicator } from './ThinkingIndicator'
import { ModeBar } from './ModeBar'
import { CookEntryModal } from './CookEntryModal'
import { HandoffCard } from './HandoffCard'
import { apiStream, apiRequest, pollJob } from '../../lib/api'
import { useChatContext } from '../../context/ChatContext'
import type { ActiveContext, HandoffResult } from '../../types/chat'

interface ChatViewProps {
  messages: Message[]
  setMessages: Dispatch<SetStateAction<Message[]>>
  onOpenFocus: (item: { type: string; id: string }) => void
  setActiveJobId: Dispatch<SetStateAction<string | null>>
  jobLoading: boolean
  setJobLoading: Dispatch<SetStateAction<boolean>>
}

export function ChatView({ messages, setMessages, onOpenFocus, setActiveJobId, jobLoading, setJobLoading }: ChatViewProps) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  // V10: Phase-based progress tracking (graph modes only)
  const [phaseState, setPhaseState] = useState(createInitialPhaseState())
  // V10: Active context state - can be used in future for persistent context bar
  const [, setActiveContext] = useState<ActiveContext | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const { getAndClearUIChanges, activeMode, setActiveMode, setCookRecipeName } = useChatContext()
  // Track initial message count to avoid scrolling on mount
  const initialMessageCount = useRef(messages.length)

  // Cook/Brainstorm streaming state
  const [streamingText, setStreamingText] = useState('')
  const [showCookEntry, setShowCookEntry] = useState(false)
  const [handoffResult, setHandoffResult] = useState<HandoffResult | null>(null)
  const [cookInit, setCookInit] = useState<{ recipe_id: string; notes: string } | null>(null)
  const [brainstormInit, setBrainstormInit] = useState(false)

  // Ref for programmatic send (exit buttons, cook entry)
  const handleSendRef = useRef<(() => void) | null>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const isNearBottom = () => {
    const container = messagesContainerRef.current
    if (!container) return true
    const threshold = 100 // px from bottom
    return container.scrollHeight - container.scrollTop - container.clientHeight < threshold
  }

  // Track previous streaming text length to detect clears vs. new content
  const prevStreamingLen = useRef(0)

  useEffect(() => {
    // Only scroll when NEW messages are added after mount, not on initial render
    // This prevents mobile Chrome from triggering address bar hide on load
    const streamingCleared = prevStreamingLen.current > 0 && streamingText.length === 0
    prevStreamingLen.current = streamingText.length

    // Don't scroll when streaming text is cleared — the DOM is shrinking,
    // and scrolling now pushes the input to the top with a blank screen
    if (streamingCleared) return

    if (messages.length > initialMessageCount.current && isNearBottom()) {
      scrollToBottom()
    }
  }, [messages, phaseState, streamingText, handoffResult])

  const handleSend = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!input.trim() || loading || jobLoading) return

    const userMessage = input.trim()
    setInput('')
    setLoading(true)
    // Reset phase state for new request
    setPhaseState(createInitialPhaseState())
    setStreamingText('')

    // Add user message (skip for exit signals)
    const isExitSignal = userMessage === '__cook_exit__' || userMessage === '__brainstorm_exit__'
    if (!isExitSignal) {
      const userMsg: Message = {
        id: Date.now().toString(),
        role: 'user',
        content: userMessage,
      }
      setMessages((prev) => [...prev, userMsg])
    }

    let currentJobId: string | null = null
    let receivedDone = false
    const isStreamingMode = activeMode === 'cook' || activeMode === 'brainstorm'

    // Capture init values before clearing (they're React state, read synchronously)
    const currentCookInit = cookInit
    const currentBrainstormInit = brainstormInit

    try {
      // Get and clear UI changes to include with this message
      const uiChanges = getAndClearUIChanges()

      // Build request body
      const body: Record<string, unknown> = {
        message: userMessage,
        log_prompts: true,
        mode: activeMode,
        ui_changes: uiChanges.length > 0 ? uiChanges : undefined,
      }

      // Cook first turn
      if (currentCookInit) {
        body.cook_init = currentCookInit
        setCookInit(null)
      }

      // Brainstorm first turn
      if (currentBrainstormInit) {
        body.brainstorm_init = true
        setBrainstormInit(false)
      }

      const res = await apiStream('/api/chat/stream', {
        method: 'POST',
        body: JSON.stringify(body),
      })

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = 'progress'
      let latestActiveContext: ActiveContext | null = null
      let localPhaseState = createInitialPhaseState()
      let localStreamingText = ''

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

              if (currentEvent === 'job_started') {
                // Capture job_id early so we can poll on disconnect
                currentJobId = data.job_id
              } else if (currentEvent === 'chunk') {
                // Cook/Brainstorm streaming tokens
                localStreamingText += data.content
                setStreamingText(localStreamingText)
              } else if (currentEvent === 'handoff') {
                // Mode exit handoff summary
                setHandoffResult({
                  summary: data.summary,
                  action: data.action,
                  actionDetail: data.action_detail,
                  recipeContent: data.recipe_content || null,
                })
              } else if (currentEvent === 'done') {
                receivedDone = true
                // Track job_id from done event (fallback if job_started missed)
                if (data.job_id) {
                  currentJobId = data.job_id
                }

                if (isStreamingMode) {
                  // Cook/Brainstorm: use accumulated streaming text
                  const responseContent = localStreamingText || data.response
                  if (responseContent) {
                    const assistantMsg: Message = {
                      id: Date.now().toString(),
                      role: 'assistant',
                      content: responseContent,
                    }
                    setMessages((prev) => [...prev, assistantMsg])
                  }
                  setStreamingText('')

                  // If this was an exit, reset mode
                  if (isExitSignal) {
                    setActiveMode('plan')
                    setCookRecipeName(null)
                  }
                } else {
                  // Graph modes (plan/quick): existing behavior
                  if (data.active_context) {
                    latestActiveContext = data.active_context
                    setActiveContext(latestActiveContext)
                  }
                  const assistantMsg: Message = {
                    id: Date.now().toString(),
                    role: 'assistant',
                    content: data.response,
                    activeContext: latestActiveContext || undefined,
                    reasoning: localPhaseState.steps.length > 0 ? localPhaseState : undefined,
                  }
                  setMessages((prev) => [...prev, assistantMsg])
                }

                setPhaseState(createInitialPhaseState())

                // Acknowledge the job
                if (currentJobId) {
                  apiRequest(`/api/jobs/${currentJobId}/ack`, { method: 'POST' }).catch(() => {})
                }
              } else if (currentEvent === 'error') {
                throw new Error(data.error)
              } else {
                // Graph mode progress events
                const eventData = {
                  type: data.type || currentEvent,
                  ...data,
                }
                if (eventData.type === 'active_context') {
                  latestActiveContext = data.data || data
                  setActiveContext(latestActiveContext)
                }
                localPhaseState = updatePhaseState(localPhaseState, eventData)
                setPhaseState(localPhaseState)
              }
            } catch {
              // Ignore parse errors
            }
          }
        }
      }

      // If stream ended without a done event, try to recover via job polling
      if (!receivedDone && currentJobId) {
        await recoverFromJob(currentJobId)
      }
    } catch (err) {
      // Stream disconnected — try to recover via job polling if we have a job_id
      // If no job_id yet, next page load will recover via loadConversation()
      if (currentJobId) {
        await recoverFromJob(currentJobId)
      } else {
        const errorMsg: Message = {
          id: Date.now().toString(),
          role: 'assistant',
          content: `Sorry, something went wrong: ${err instanceof Error ? err.message : 'Unknown error'}`,
        }
        setMessages((prev) => [...prev, errorMsg])
        setPhaseState(createInitialPhaseState())
        setStreamingText('')
      }
    } finally {
      setLoading(false)
    }
  }

  // Keep ref updated for programmatic sends
  handleSendRef.current = handleSend

  const recoverFromJob = async (jobId: string) => {
    try {
      setActiveJobId(jobId)
      setJobLoading(true)
      const finishedJob = await pollJob(jobId)
      if (finishedJob.status === 'complete' && finishedJob.output) {
        const recoveredMsg: Message = {
          id: `recovered-${finishedJob.id}`,
          role: 'assistant',
          content: finishedJob.output.response,
        }
        setMessages((prev) => [...prev, recoveredMsg])
        await apiRequest(`/api/jobs/${finishedJob.id}/ack`, { method: 'POST' })
      }
      setPhaseState(createInitialPhaseState())
    } catch {
      // Recovery failed — response may be picked up on next page load
    } finally {
      setJobLoading(false)
      setActiveJobId(null)
    }
  }

  // Determine if we should show graph progress (has any activity)
  const hasProgress = phaseState.understand.context ||
    phaseState.think.complete ||
    phaseState.steps.length > 0

  const isStreamingMode = activeMode === 'cook' || activeMode === 'brainstorm'

  // Placeholder text varies by mode
  const placeholder = activeMode === 'cook'
    ? "What's cooking?"
    : activeMode === 'brainstorm'
      ? 'What are you thinking about?'
      : 'Ask Alfred anything...'

  return (
    <div className="h-full flex flex-col">
      {/* Messages */}
      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4">
        <div className="max-w-2xl mx-auto space-y-4">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onOpenFocus={onOpenFocus}
            />
          ))}

          {/* Cook/Brainstorm: streaming text display */}
          {loading && isStreamingMode && (
            <div className="py-2">
              <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4">
                {streamingText ? (
                  <div className="text-[var(--color-text-primary)] whitespace-pre-wrap text-sm">
                    {streamingText}
                    <span className="animate-pulse ml-0.5">&#9612;</span>
                  </div>
                ) : (
                  <ThinkingIndicator label={activeMode === 'cook' ? 'Cooking...' : 'Thinking...'} />
                )}
              </div>
            </div>
          )}

          {/* Graph modes: inline streaming progress */}
          {loading && hasProgress && !isStreamingMode && (
            <div className="py-2">
              <StreamingProgress
                phase={phaseState}
                mode={activeMode === 'quick' ? 'quick' : 'plan'}
              />
            </div>
          )}

          {/* Graph modes: initial loading state before any events */}
          {loading && !hasProgress && !isStreamingMode && !jobLoading && (
            <div className="py-2">
              <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4">
                <div className="flex items-center gap-2 text-sm text-[var(--color-accent)]">
                  <span className="w-4 text-center">&#9679;</span>
                  <span>{activeMode === 'quick' ? 'Working...' : 'Understanding...'}</span>
                </div>
              </div>
            </div>
          )}

          {/* Handoff card on mode exit */}
          {handoffResult && (
            <div className="py-2">
              <HandoffCard
                {...handoffResult}
                onDismiss={() => setHandoffResult(null)}
              />
            </div>
          )}

          {/* Job recovery: polling a running job */}
          {jobLoading && (
            <div className="py-2">
              <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4">
                <div className="flex items-center gap-2 text-sm text-[var(--color-accent)]">
                  <span className="w-4 text-center">&#9679;</span>
                  <span>Alfred is still working...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area - Fixed at bottom */}
      <div className="bg-[var(--color-bg-primary)] px-4 py-3 flex-shrink-0">
        <div className="max-w-2xl mx-auto">
          <ModeBar
            onCookClick={() => setShowCookEntry(true)}
            onBrainstormClick={() => {
              setActiveMode('brainstorm')
              setBrainstormInit(true)
            }}
            onSendExit={(exitMsg) => {
              setInput(exitMsg)
              setTimeout(() => handleSendRef.current?.(), 0)
            }}
            disabled={loading || jobLoading}
          />
          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={handleSend}
            disabled={loading || jobLoading}
            placeholder={placeholder}
          />
        </div>
      </div>

      {/* Cook entry modal */}
      <CookEntryModal
        isOpen={showCookEntry}
        onClose={() => setShowCookEntry(false)}
        onStart={(recipeId, recipeName, notes) => {
          setShowCookEntry(false)
          setActiveMode('cook')
          setCookInit({ recipe_id: recipeId, notes })
          setCookRecipeName(recipeName)
          setInput(notes || 'Ready to cook!')
          setTimeout(() => handleSendRef.current?.(), 0)
        }}
      />
    </div>
  )
}
