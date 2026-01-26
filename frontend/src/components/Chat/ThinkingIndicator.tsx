/**
 * ThinkingIndicator - Subtle pulsing dots for AI thinking state
 *
 * Design: Three terracotta dots that pulse in sequence
 * Philosophy: Smooth and professional, not bouncy or playful
 */

interface ThinkingIndicatorProps {
  /** Optional label to show next to dots */
  label?: string
  /** Size variant */
  size?: 'sm' | 'md' | 'lg'
}

export function ThinkingIndicator({
  label,
  size = 'md',
}: ThinkingIndicatorProps) {
  const dotSizes = {
    sm: 'w-1.5 h-1.5',
    md: 'w-2 h-2',
    lg: 'w-2.5 h-2.5',
  }

  const gapSizes = {
    sm: 'gap-1',
    md: 'gap-1.5',
    lg: 'gap-2',
  }

  const textSizes = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  }

  return (
    <div className="flex items-center gap-2">
      <div className={`flex items-center ${gapSizes[size]}`}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={`
              ${dotSizes[size]}
              rounded-full
              bg-[var(--color-accent)]
            `}
            style={{
              animation: 'thinking-pulse 1.2s ease-in-out infinite',
              animationDelay: `${i * 0.2}s`,
            }}
            aria-hidden="true"
          />
        ))}
      </div>
      {label && (
        <span className={`text-[var(--color-text-muted)] ${textSizes[size]}`}>
          {label}
        </span>
      )}
      <span className="sr-only">Alfred is thinking</span>
    </div>
  )
}

export default ThinkingIndicator
