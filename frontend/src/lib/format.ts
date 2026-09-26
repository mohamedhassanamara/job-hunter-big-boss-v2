import type { ContactTier, RemoteType, Source, Stage } from './types'

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'short' })

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—'
  const diff = new Date(iso).getTime() - now
  const abs = Math.abs(diff)
  const min = 60_000
  const hour = 60 * min
  const day = 24 * hour
  if (abs < min) return 'just now'
  if (abs < hour) return rtf.format(Math.round(diff / min), 'minute')
  if (abs < day) return rtf.format(Math.round(diff / hour), 'hour')
  if (abs < 30 * day) return rtf.format(Math.round(diff / day), 'day')
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

/** Compact age like "3h", "2d" for dense rows. */
export function shortAge(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—'
  const diff = Math.max(0, now - new Date(iso).getTime())
  const h = diff / 3_600_000
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m`
  if (h < 24) return `${Math.round(h)}h`
  const d = h / 24
  if (d < 30) return `${Math.round(d)}d`
  return `${Math.round(d / 30)}mo`
}

export function absoluteDate(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function clockTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export const SOURCE_LABELS: Record<Source, string> = {
  adzuna: 'Adzuna',
  remotive: 'Remotive',
  arbeitnow: 'Arbeitnow',
  wttj: 'Welcome to the Jungle',
}

export const SOURCE_SHORT: Record<Source, string> = {
  adzuna: 'Adzuna',
  remotive: 'Remotive',
  arbeitnow: 'Arbeitnow',
  wttj: 'WTTJ',
}

export const REMOTE_LABELS: Record<RemoteType, string> = {
  remote: 'Remote',
  hybrid: 'Hybrid',
  onsite: 'On-site',
  unknown: 'Unknown',
}

export const TIER_LABELS: Record<ContactTier, string> = {
  apollo_dump: 'Apollo import',
  lookup_queued: 'Lookup queued',
  lookup_found: 'Apollo lookup',
  none: 'No contact',
}

export const STAGE_ORDER: Stage[] = [
  'new',
  'shortlisted',
  'cv_ready',
  'ready',
  'done',
  'interview',
  'closed',
]

export const STAGE_LABELS: Record<Stage, string> = {
  new: 'New',
  shortlisted: 'Shortlisted',
  cv_ready: 'CV ready',
  ready: 'Ready',
  done: 'Sent / Applied',
  interview: 'Interview',
  closed: 'Closed',
}

export const COLUMN_LABELS: Record<Stage, string> = {
  ...STAGE_LABELS,
  ready: 'Ready to send / apply',
}

export const COUNTRY_LABELS: Record<string, string> = {
  ES: 'Spain',
  PT: 'Portugal',
  FR: 'France',
  IT: 'Italy',
  REMOTE: 'Remote / EU',
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

export function pluralize(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}
