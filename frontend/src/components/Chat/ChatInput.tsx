import { FormEvent, KeyboardEvent, useState, useRef, useEffect, useCallback } from 'react'
import { useAuth } from '../../hooks/useAuth'

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSubmit: (e?: FormEvent) => void
  disabled?: boolean
  placeholder?: string
}

// API response types
interface EntityItem {
  id: string
  label: string
}

interface EntityGroup {
  type: string
  label: string
  items: EntityItem[]
}

interface EntitySearchResponse {
  groups: EntityGroup[]
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = 'Ask Alfred anything...',
}: ChatInputProps) {
  const { session } = useAuth()
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // @-mention state
  const [showMentionDropdown, setShowMentionDropdown] = useState(false)
  const [mentionSearch, setMentionSearch] = useState('')
  const [mentionStartPos, setMentionStartPos] = useState<number | null>(null)
  const [mentionResults, setMentionResults] = useState<EntityGroup[]>([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [isSearching, setIsSearching] = useState(false)
  const mentionDropdownRef = useRef<HTMLDivElement>(null)

  // Close mention dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (mentionDropdownRef.current && !mentionDropdownRef.current.contains(e.target as Node)) {
        setShowMentionDropdown(false)
        setMentionStartPos(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Debounced search for @-mentions
  useEffect(() => {
    if (!showMentionDropdown || !session?.access_token) return

    const timer = setTimeout(async () => {
      setIsSearching(true)
      try {
        const params = new URLSearchParams()
        if (mentionSearch) params.set('q', mentionSearch)

        const response = await fetch(`/api/context/entities?${params}`, {
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        })

        if (response.ok) {
          const data: EntitySearchResponse = await response.json()
          setMentionResults(data.groups)
          setSelectedIndex(0)
        }
      } catch (error) {
        console.error('Mention search failed:', error)
      } finally {
        setIsSearching(false)
      }
    }, 200) // 200ms debounce

    return () => clearTimeout(timer)
  }, [mentionSearch, showMentionDropdown, session?.access_token])

  // Flatten results for keyboard navigation
  const flattenedItems = mentionResults.flatMap(group =>
    group.items.map(item => ({ ...item, type: group.type, groupLabel: group.label }))
  )

  // Handle text input changes - detect @ trigger
  const handleChange = useCallback((newValue: string) => {
    onChange(newValue)

    // Use setTimeout to ensure cursor position is updated after React render
    setTimeout(() => {
      const textarea = textareaRef.current
      if (!textarea) return

      const cursorPos = textarea.selectionStart
      const textBeforeCursor = newValue.slice(0, cursorPos)

      // Check if we just typed @ or are in an @-mention context
      const lastAtIndex = textBeforeCursor.lastIndexOf('@')

      if (lastAtIndex !== -1) {
        // Check if @ is at start or preceded by whitespace
        const charBefore = lastAtIndex > 0 ? textBeforeCursor[lastAtIndex - 1] : ' '
        if (charBefore === ' ' || charBefore === '\n' || lastAtIndex === 0) {
          // Extract search text after @
          const searchText = textBeforeCursor.slice(lastAtIndex + 1)

          // Only show dropdown if no space after @ (still typing entity name)
          if (!searchText.includes(' ') && !searchText.includes('\n')) {
            setMentionStartPos(lastAtIndex)
            setMentionSearch(searchText)
            setShowMentionDropdown(true)
            return
          }
        }
      }

      // Close dropdown if not in @ context
      setShowMentionDropdown(false)
      setMentionStartPos(null)
    }, 0)
  }, [onChange])

  // Insert mention at cursor position
  const insertMention = useCallback((item: { id: string; label: string; type: string }) => {
    if (mentionStartPos === null) return

    // Format: @[Label](type:uuid)
    const mention = `@[${item.label}](${item.type}:${item.id})`

    // Replace @searchText with the mention
    const beforeAt = value.slice(0, mentionStartPos)
    const cursorPos = textareaRef.current?.selectionStart ?? value.length
    const afterSearch = value.slice(cursorPos)

    const newValue = beforeAt + mention + ' ' + afterSearch
    onChange(newValue)

    // Close dropdown
    setShowMentionDropdown(false)
    setMentionStartPos(null)
    setMentionSearch('')

    // Focus back on textarea
    setTimeout(() => {
      textareaRef.current?.focus()
      const newCursorPos = beforeAt.length + mention.length + 1
      textareaRef.current?.setSelectionRange(newCursorPos, newCursorPos)
    }, 0)
  }, [mentionStartPos, value, onChange])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Handle mention dropdown navigation
    if (showMentionDropdown && flattenedItems.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex(prev => (prev + 1) % flattenedItems.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex(prev => (prev - 1 + flattenedItems.length) % flattenedItems.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        insertMention(flattenedItems[selectedIndex])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setShowMentionDropdown(false)
        setMentionStartPos(null)
        return
      }
    }

    // Normal Enter handling (submit)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit()
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex gap-3 items-center relative">
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          rows={1}
          className="w-full px-4 py-2.5 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] resize-none focus:border-[var(--color-accent)] focus:outline-none disabled:opacity-50 shadow-sm"
        />

        {/* @-mention dropdown */}
        {showMentionDropdown && (
          <div
            ref={mentionDropdownRef}
            className="absolute bottom-full left-0 mb-2 w-80 max-h-64 overflow-y-auto bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-lg z-50"
          >
            {isSearching && mentionResults.length === 0 ? (
              <div className="px-4 py-3 text-[var(--color-text-muted)] text-sm">
                Searching...
              </div>
            ) : flattenedItems.length === 0 ? (
              <div className="px-4 py-3 text-[var(--color-text-muted)] text-sm">
                No matches found
              </div>
            ) : (
              <>
                {mentionResults.map((group) => (
                  <div key={group.type}>
                    {/* Group header */}
                    <div className="px-3 py-1.5 text-xs font-semibold text-[var(--color-text-muted)] uppercase bg-[var(--color-bg-tertiary)] border-b border-[var(--color-border)]">
                      {group.label}
                    </div>
                    {/* Group items */}
                    {group.items.map((item) => {
                      const flatIndex = flattenedItems.findIndex(
                        f => f.id === item.id && f.type === group.type
                      )
                      const isSelected = flatIndex === selectedIndex

                      return (
                        <button
                          key={`${group.type}-${item.id}`}
                          type="button"
                          onClick={() => insertMention({ ...item, type: group.type })}
                          className={`w-full px-4 py-2 text-left text-sm transition-colors ${
                            isSelected
                              ? 'bg-[var(--color-accent)] text-[var(--color-text-inverse)]'
                              : 'text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)]'
                          }`}
                        >
                          {item.label}
                        </button>
                      )
                    })}
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>

      {/* Send button */}
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="px-5 py-2.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-semibold rounded-[var(--radius-lg)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
      >
        Send
      </button>
    </form>
  )
}
