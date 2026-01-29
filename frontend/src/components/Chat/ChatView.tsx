import { useState, useRef, useEffect, FormEvent, Dispatch, SetStateAction } from 'react'
import { MessageBubble, Message } from './MessageBubble'
import { ChatInput } from './ChatInput'
import {
  StreamingProgress,
  createInitialPhaseState,
  updatePhaseState,
} from './StreamingProgress'
import { Mode } from '../../App'
import { apiStream, apiRequest, pollJob } from '../../lib/api'
import { useChatContext } from '../../context/ChatContext'
import type { ActiveContext } from '../../types/chat'

interface ChatViewProps {
  messages: Message[]
  setMessages: Dispatch<SetStateAction<Message[]>>
  onOpenFocus: (item: { type: string; id: string }) => void
  mode: Mode
  setActiveJobId: Dispatch<SetStateAction<string | null>>
  jobLoading: boolean
  setJobLoading: Dispatch<SetStateAction<boolean>>
}

export function ChatView({ messages, setMessages, onOpenFocus, mode, setActiveJobId, jobLoading, setJobLoading }: ChatViewProps) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  // V10: Phase-based progress tracking
  const [phaseState, setPhaseState] = useState(createInitialPhaseState())
  // V10: Active context state - can be used in future for persistent context bar
  const [, setActiveContext] = useState<ActiveContext | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const { getAndClearUIChanges } = useChatContext()
  // Track initial message count to avoid scrolling on mount
  const initialMessageCount = useRef(messages.length)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const isNearBottom = () => {
    const container = messagesContainerRef.current
    if (!container) return true
    const threshold = 100 // px from bottom
    return container.scrollHeight - container.scrollTop - container.clientHeight < threshold
  }

  useEffect(() => {
    // Only scroll when NEW messages are added after mount, not on initial render
    // This prevents mobile Chrome from triggering address bar hide on load
    if (messages.length > initialMessageCount.current && isNearBottom()) {
      scrollToBottom()
    }
  }, [messages, phaseState])

  const handleSend = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!input.trim() || loading || jobLoading) return

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

    let currentJobId: string | null = null
    let receivedDone = false

    try {
      // Get and clear UI changes to include with this message
      const uiChanges = getAndClearUIChanges()

      const res = await apiStream('/api/chat/stream', {
        method: 'POST',
        body: JSON.stringify({
          message: userMessage,
          log_prompts: true,
          mode: mode,
          ui_changes: uiChanges.length > 0 ? uiChanges : undefined,
        }),
      })

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = 'progress'
      let latestActiveContext: ActiveContext | null = null
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

              if (currentEvent === 'job_started') {
                // Capture job_id early so we can poll on disconnect
                currentJobId = data.job_id
              } else if (currentEvent === 'done') {
                receivedDone = true
                // Track job_id from done event (fallback if job_started missed)
                if (data.job_id) {
                  currentJobId = data.job_id
                }
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
                setPhaseState(createInitialPhaseState())
                // Acknowledge the job
                if (currentJobId) {
                  apiRequest(`/api/jobs/${currentJobId}/ack`, { method: 'POST' }).catch(() => {})
                }
              } else if (currentEvent === 'error') {
                throw new Error(data.error)
              } else {
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
      }
    } finally {
      setLoading(false)
    }
  }

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

  // Determine if we should show progress (has any activity)
  const hasProgress = phaseState.understand.context ||
    phaseState.think.complete ||
    phaseState.steps.length > 0

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
          {loading && !hasProgress && !jobLoading && (
            <div className="py-2">
              <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4">
                <div className="flex items-center gap-2 text-sm text-[var(--color-accent)]">
                  <span className="w-4 text-center">●</span>
                  <span>{mode === 'quick' ? 'Working...' : 'Understanding...'}</span>
                </div>
              </div>
            </div>
          )}

          {/* Job recovery: polling a running job */}
          {jobLoading && (
            <div className="py-2">
              <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4">
                <div className="flex items-center gap-2 text-sm text-[var(--color-accent)]">
                  <span className="w-4 text-center">●</span>
                  <span>Alfred is still working...</span>
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
            disabled={loading || jobLoading}
            placeholder="Ask Alfred anything..."
          />
        </div>
      </div>
    </div>
  )
}
