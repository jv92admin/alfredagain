export interface ProgressStep {
  label: string
  status: 'pending' | 'active' | 'completed'
}

interface ProgressTrailProps {
  steps: ProgressStep[]
}

export function ProgressTrail({ steps }: ProgressTrailProps) {
  return (
    <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4">
      <div className="space-y-2">
        {steps.map((step, i) => (
          <div
            key={i}
            className={`flex items-center gap-2 text-sm ${
              step.status === 'completed'
                ? 'text-[var(--color-success)]'
                : step.status === 'active'
                ? 'text-[var(--color-accent)]'
                : 'text-[var(--color-text-muted)] opacity-50'
            }`}
          >
            <span className="w-4 text-center">
              {step.status === 'completed' ? '✓' : step.status === 'active' ? '◐' : '○'}
            </span>
            <span>{step.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

