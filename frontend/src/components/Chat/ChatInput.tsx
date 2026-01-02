import { FormEvent, KeyboardEvent, useState, useRef, useEffect } from 'react'
import { Mode } from '../../App'

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSubmit: (e?: FormEvent) => void
  disabled?: boolean
  placeholder?: string
  mode: Mode
  onModeChange: (mode: Mode) => void
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = 'Ask Alfred anything...',
  mode,
  onModeChange,
}: ChatInputProps) {
  const [showModeMenu, setShowModeMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowModeMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit()
    }
  }

  const modeLabels: Record<Mode, string> = {
    quick: '⚡',
    plan: '📋',
  }

  const modeDescriptions: Record<Mode, string> = {
    quick: 'Quick — Fast, direct answers',
    plan: 'Plan — Detailed, step-by-step',
  }

  return (
    <form onSubmit={onSubmit} className="flex gap-2 items-end">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        rows={1}
        className="flex-1 px-4 py-3 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] resize-none focus:border-[var(--color-accent)] focus:outline-none disabled:opacity-50"
      />
      
      {/* Mode selector + Send button group */}
      <div className="flex items-stretch" ref={menuRef}>
        {/* Mode dropdown trigger */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowModeMenu(!showModeMenu)}
            className="h-full px-3 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] border-r-0 rounded-l-[var(--radius-md)] text-lg hover:bg-[var(--color-bg-secondary)] transition-colors"
            title={modeDescriptions[mode]}
          >
            {modeLabels[mode]}
          </button>
          
          {/* Dropdown menu */}
          {showModeMenu && (
            <div className="absolute bottom-full left-0 mb-2 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-lg overflow-hidden min-w-[180px] z-50">
              {(Object.keys(modeLabels) as Mode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    onModeChange(m)
                    setShowModeMenu(false)
                  }}
                  className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 hover:bg-[var(--color-bg-tertiary)] transition-colors ${
                    mode === m ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-primary)]'
                  }`}
                >
                  <span>{modeLabels[m]}</span>
                  <span>{modeDescriptions[m]}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        
        {/* Send button */}
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="px-5 py-3 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-semibold rounded-r-[var(--radius-md)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </div>
    </form>
  )
}
