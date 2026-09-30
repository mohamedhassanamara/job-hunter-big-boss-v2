import type { Tone } from '@/components/app/badges'
import type { DraftStatus } from './types'

export const DRAFT_STATUS: Record<DraftStatus, { tone: Tone; label: string }> = {
  draft: { tone: 'amber', label: 'Needs review' },
  approved: { tone: 'blue', label: 'Approved' },
  queued: { tone: 'blue', label: 'Queued' },
  sent: { tone: 'green', label: 'Sent' },
  rejected: { tone: 'gray', label: 'Rejected' },
  failed: { tone: 'red', label: 'Failed' },
}
