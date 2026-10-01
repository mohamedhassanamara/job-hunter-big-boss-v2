import type { Tone } from '@/components/app/badges'
import type { Tracks } from '@/lib/types'

/** A LinkedIn job search by geoId (mirrors backend services/linkedin.search_url): used by
 * Settings → LinkedIn's "Test link" so you can see where a geoId lands. */
export function linkedinSearchUrl(role: string, geoId: string): string {
  const params = new URLSearchParams({ keywords: role, geoId, f_TPR: 'r86400', sortBy: 'DD' })
  return `https://www.linkedin.com/jobs/search/?${params.toString().replace(/\+/g, '%20')}`
}

/** LinkedIn track labels (furthest person on the job). */
export const LINKEDIN_TRACK: Record<Tracks['linkedin'], { label: string; tone: Tone }> = {
  none: { label: 'Nobody yet', tone: 'gray' },
  to_contact: { label: 'To contact', tone: 'blue' },
  sent: { label: 'Request sent', tone: 'amber' },
  accepted: { label: 'Accepted', tone: 'teal' },
  messaged: { label: 'Messaged', tone: 'violet' },
  replied: { label: 'Replied', tone: 'green' },
}
