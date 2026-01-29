// Job lifecycle types for disconnect recovery (Phase 2.5)

export type JobStatus = 'pending' | 'running' | 'complete' | 'failed'

export interface Job {
  id: string
  user_id: string
  status: JobStatus
  input: {
    message: string
    mode: string
    ui_changes?: any[] | null
  }
  output?: {
    response: string
    active_context?: any
    log_dir?: string | null
  } | null
  error?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  acknowledged_at?: string | null
}

export interface ActiveJobResponse {
  job: Job | null
}

export interface JobResponse {
  job: Job
}
