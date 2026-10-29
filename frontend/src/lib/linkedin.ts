import type { Tone } from '@/components/app/badges'
import type { Tracks } from '@/lib/types'

/** LinkedIn track labels (furthest person on the job). */
export const LINKEDIN_TRACK: Record<Tracks['linkedin'], { label: string; tone: Tone }> = {
  none: { label: 'Nobody yet', tone: 'gray' },
  to_contact: { label: 'To contact', tone: 'blue' },
  sent: { label: 'Request sent', tone: 'amber' },
  accepted: { label: 'Accepted', tone: 'teal' },
  messaged: { label: 'Messaged', tone: 'violet' },
  replied: { label: 'Replied', tone: 'green' },
}
