import type { ContactTier, FitBand, RemoteType, Source, Stage } from './types'

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
  boards: 'Company job boards',
  bayt: 'Bayt',
}

export const SOURCE_SHORT: Record<Source, string> = {
  adzuna: 'Adzuna',
  remotive: 'Remotive',
  arbeitnow: 'Arbeitnow',
  wttj: 'WTTJ',
  boards: 'Company',
  bayt: 'Bayt',
}

export const REMOTE_LABELS: Record<RemoteType, string> = {
  remote: 'Remote',
  hybrid: 'Hybrid',
  onsite: 'On-site',
  unknown: 'Unknown',
}

export const TIER_LABELS: Record<ContactTier, string> = {
  imported: 'Imported',
  found: 'Found by you',
  to_get: 'Contact to get',
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
  done: 'Applied / emailed',
  interview: 'Interview',
  closed: 'Closed',
}

export const COLUMN_LABELS: Record<Stage, string> = {
  ...STAGE_LABELS,
  ready: 'Ready to send / apply',
}

const regionNames = new Intl.DisplayNames(['en'], { type: 'region' })

/** English name for an ISO country code ('AE' → 'United Arab Emirates'). REMOTE = no country. */
export function countryName(code: string): string {
  if (code === 'REMOTE') return 'Remote (no country)'
  try {
    return regionNames.of(code) ?? code
  } catch {
    return code
  }
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

/** Mirrors backend services.views.fit_band. */
export function fitBand(score: number): FitBand {
  return score >= 80 ? 'strong' : score >= 65 ? 'good' : score >= 50 ? 'fair' : 'weak'
}

/** Human label for a pre-filter reason code (see backend services/prefilter.py). */
export function reasonLabel(reason: string): string {
  const [code, arg] = reason.split(':', 2)
  switch (code) {
    case 'title_no_role_match':
      return "Title doesn't match a target role"
    case 'title_excluded':
      return `Title contains “${arg}”`
    case 'location_outside':
      return arg === 'unknown'
        ? 'Location unknown / outside targets'
        : `Outside target countries (${countryName(arg)})`
    case 'remote_outside':
      return arg === 'unknown' ? 'Remote region outside your remote scope' : `Remote limited to ${countryName(arg)} (outside your remote scope)`
    case 'too_old':
      return 'Posted too long ago'
    case 'not_remote':
      return 'Not remote'
    case 'incomplete':
      return 'Missing title, company or link'
    default:
      return reason
  }
}

/** "34 fetched · 12 new · 9 filtered · 3 duplicates" */
export function runSummary(t: Partial<Record<string, number>>): string {
  const parts = [
    `${t.fetched ?? 0} fetched`,
    `${t.new ?? 0} new`,
    `${t.filtered ?? 0} filtered`,
    pluralize(t.duplicate ?? 0, 'duplicate'),
  ]
  if (t.updated) parts.splice(2, 0, `${t.updated} updated`)
  return parts.join(' · ')
}

/** "about 45s" · "about 12 min" · "about 1h 10m" (rescore estimates). */
export function formatDuration(seconds: number | null): string {
  if (seconds == null) return 'unknown time'
  if (seconds < 90) return `about ${Math.max(1, Math.round(seconds))}s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 90) return `about ${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `about ${h}h${m ? ` ${m}m` : ''}`
}
