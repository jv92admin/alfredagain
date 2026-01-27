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
}
