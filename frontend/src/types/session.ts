// Session management types

export type SessionStatus = 'active' | 'stale' | 'none'

export interface SessionPreview {
  last_message: string
  message_count: number
}

export interface SessionStatusResponse {
  status: SessionStatus
  last_active_at: string | null
  preview: SessionPreview | null
  messages: Array<{ id: string; role: 'user' | 'assistant'; content: string }>
  active_job: { id: string; status: string } | null
}
