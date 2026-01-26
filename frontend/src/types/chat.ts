// V10: Active context types for streaming entity display

export interface ActiveContextEntity {
  ref: string
  type: string
  label: string
  action: 'read' | 'created' | 'generated' | 'linked' | 'updated' | string
  turnCreated: number
  turnLastRef: number
  isGenerated: boolean
  retentionReason?: string
}

export interface ActiveContext {
  entities: ActiveContextEntity[]
  currentTurn: number
  changes: {
    added: string[]
  }
}
