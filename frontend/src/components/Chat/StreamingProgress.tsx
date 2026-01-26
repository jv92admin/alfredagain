import { ActiveContextDisplay } from './ActiveContextDisplay'
import type { ActiveContext } from '../../types/chat'

// Tool call info from step_complete event
interface ToolCall {
  tool: string
  table: string
  count: number
}

// Phase-level state tracking
interface PhaseState {
  understand: {
    complete: boolean
    context?: ActiveContext
  }
  think: {
    complete: boolean
    goal?: string
    stepCount?: number
  }
  steps: StepState[]
  currentStepIndex: number
}

interface StepState {
  index: number
  description: string
  status: 'pending' | 'active' | 'completed'
  toolCalls?: ToolCall[]
  context?: ActiveContext
}

interface StreamingProgressProps {
  phase: PhaseState
  mode: 'plan' | 'quick'
}

// Tool name display mapping
const TOOL_DISPLAY: Record<string, string> = {
  read: 'read',
  create: 'create',
  update: 'update',
  delete: 'delete',
  upsert: 'upsert',
}

function ToolCallDisplay({ toolCalls }: { toolCalls: ToolCall[] }) {
  return (
    <div className="pl-6 text-xs text-[var(--color-text-muted)] space-y-0.5">
      {toolCalls.map((tc, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="opacity-60">→</span>
          <span>{TOOL_DISPLAY[tc.tool] || tc.tool}({tc.table})</span>
          <span className="opacity-60">• {tc.count} {tc.count === 1 ? 'item' : 'items'}</span>
        </div>
      ))}
    </div>
  )
}

function PhaseHeader({
  label,
  status,
  detail,
}: {
  label: string
  status: 'pending' | 'active' | 'completed'
  detail?: string
}) {
  const statusIcon = status === 'completed' ? '✓' : status === 'active' ? '●' : '○'
  const statusColor =
    status === 'completed'
      ? 'text-[var(--color-success)]'
      : status === 'active'
      ? 'text-[var(--color-accent)]'
      : 'text-[var(--color-text-muted)] opacity-50'

  return (
    <div className={`flex items-center gap-2 text-sm ${statusColor}`}>
      <span className="w-4 text-center">{statusIcon}</span>
      <span className="font-medium">{label}</span>
      {detail && <span className="opacity-70 font-normal">{detail}</span>}
    </div>
  )
}

export function StreamingProgress({ phase, mode }: StreamingProgressProps) {
  return (
    <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 space-y-3">
      {/* Understanding Phase */}
      <div className="space-y-1">
        <PhaseHeader
          label="Understanding..."
          status={phase.understand.complete ? 'completed' : 'active'}
        />
        {phase.understand.context && (
          <div className="pl-6">
            <ActiveContextDisplay
              context={phase.understand.context}
              defaultExpanded={true}
            />
          </div>
        )}
      </div>

      {/* Planning Phase (Plan Mode only) */}
      {mode === 'plan' && (phase.think.complete || phase.think.goal) && (
        <div className="space-y-1">
          <PhaseHeader
            label="Planning..."
            status={phase.think.complete ? 'completed' : 'active'}
            detail={
              phase.think.goal
                ? `${phase.think.goal}${phase.think.stepCount ? ` (${phase.think.stepCount} steps)` : ''}`
                : undefined
            }
          />
        </div>
      )}

      {/* Working Phase (Quick Mode) */}
      {mode === 'quick' && phase.steps.length === 0 && !phase.think.complete && (
        <PhaseHeader label="Working..." status="active" />
      )}

      {/* Act Steps */}
      {phase.steps.map((step) => (
        <div key={step.index} className="space-y-1">
          <PhaseHeader
            label={`Step ${step.index + 1}`}
            status={step.status}
            detail={step.description}
          />
          {step.toolCalls && step.toolCalls.length > 0 && (
            <ToolCallDisplay toolCalls={step.toolCalls} />
          )}
          {step.context && (
            <div className="pl-6">
              <ActiveContextDisplay
                context={step.context}
                defaultExpanded={false}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// Helper to create initial phase state
export function createInitialPhaseState(): PhaseState {
  return {
    understand: { complete: false },
    think: { complete: false },
    steps: [],
    currentStepIndex: -1,
  }
}

// Helper to update phase state based on events
export function updatePhaseState(
  state: PhaseState,
  event: { type: string; [key: string]: unknown }
): PhaseState {
  const newState = { ...state }

  switch (event.type) {
    case 'active_context':
      // Associate context with current phase
      const contextData = (event.data || event) as ActiveContext
      if (!newState.understand.complete) {
        // Still in understand phase
        newState.understand = { ...newState.understand, context: contextData }
      } else if (newState.currentStepIndex >= 0) {
        // In a step - update that step's context
        const stepIndex = newState.currentStepIndex
        if (newState.steps[stepIndex]) {
          newState.steps = [...newState.steps]
          newState.steps[stepIndex] = {
            ...newState.steps[stepIndex],
            context: contextData,
          }
        }
      }
      break

    case 'think_complete':
      newState.understand = { ...newState.understand, complete: true }
      newState.think = {
        complete: true,
        goal: event.goal as string,
        stepCount: event.stepCount as number,
      }
      break

    case 'plan':
      // Also marks understand as complete
      newState.understand = { ...newState.understand, complete: true }
      // Initialize steps from plan
      const steps = (event.steps as string[]) || []
      newState.steps = steps.map((desc, i) => ({
        index: i,
        description: desc,
        status: 'pending' as const,
      }))
      break

    case 'step':
      // Step starting
      const stepNum = (event.step as number) - 1
      newState.currentStepIndex = stepNum
      if (newState.steps[stepNum]) {
        newState.steps = [...newState.steps]
        newState.steps[stepNum] = {
          ...newState.steps[stepNum],
          status: 'active',
        }
      }
      break

    case 'step_complete':
      // Step completed
      const completedNum = (event.step as number) - 1
      if (newState.steps[completedNum]) {
        newState.steps = [...newState.steps]
        newState.steps[completedNum] = {
          ...newState.steps[completedNum],
          status: 'completed',
          toolCalls: event.tool_calls as ToolCall[] | undefined,
        }
      }
      break
  }

  return newState
}
