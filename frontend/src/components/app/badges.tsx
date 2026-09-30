import {
  CircleAlert,
  CircleDashed,
  EyeOff,
  Flag,
  Globe,
  Mail,
  MapPin,
  Search as SearchIcon,
  UserRoundCheck,
  UserRoundX,
} from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'
import { REMOTE_LABELS, SOURCE_LABELS, SOURCE_SHORT, TIER_LABELS } from '@/lib/format'
import type {
  ApplicationTrack,
  Confidence,
  ContactTier,
  FitBand,
  FitBrief,
  OutreachTrack,
  RemoteType,
  Source,
  Stage,
  Tracks,
  UserLabel,
} from '@/lib/types'
import { cn } from '@/lib/utils'

// Static class maps: Tailwind needs full class names at build time.
export type Tone = 'slate' | 'blue' | 'violet' | 'amber' | 'teal' | 'green' | 'gray' | 'red'

const TONE: Record<Tone, { dot: string; pill: string }> = {
  slate: { dot: 'bg-tone-slate-dot', pill: 'bg-tone-slate-bg text-tone-slate-fg' },
  blue: { dot: 'bg-tone-blue-dot', pill: 'bg-tone-blue-bg text-tone-blue-fg' },
  violet: { dot: 'bg-tone-violet-dot', pill: 'bg-tone-violet-bg text-tone-violet-fg' },
  amber: { dot: 'bg-tone-amber-dot', pill: 'bg-tone-amber-bg text-tone-amber-fg' },
  teal: { dot: 'bg-tone-teal-dot', pill: 'bg-tone-teal-bg text-tone-teal-fg' },
  green: { dot: 'bg-tone-green-dot', pill: 'bg-tone-green-bg text-tone-green-fg' },
  gray: { dot: 'bg-tone-gray-dot', pill: 'bg-tone-gray-bg text-tone-gray-fg' },
  red: { dot: 'bg-tone-red-dot', pill: 'bg-tone-red-bg text-tone-red-fg' },
}

export function ToneBadge({
  tone,
  children,
  dot = true,
  className,
}: {
  tone: Tone
  children: React.ReactNode
  dot?: boolean
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex h-5 shrink-0 items-center gap-1.5 rounded-sm px-1.5 text-xs font-medium whitespace-nowrap',
        TONE[tone].pill,
        className,
      )}
    >
      {dot && <span className={cn('size-1.5 rounded-full', TONE[tone].dot)} />}
      {children}
    </span>
  )
}

const STAGE_CLASSES: Record<Stage, { dot: string; pill: string }> = {
  new: { dot: 'bg-stage-new-dot', pill: 'bg-stage-new-bg text-stage-new-fg' },
  shortlisted: {
    dot: 'bg-stage-shortlisted-dot',
    pill: 'bg-stage-shortlisted-bg text-stage-shortlisted-fg',
  },
  cv_ready: { dot: 'bg-stage-cv-ready-dot', pill: 'bg-stage-cv-ready-bg text-stage-cv-ready-fg' },
  ready: { dot: 'bg-stage-ready-dot', pill: 'bg-stage-ready-bg text-stage-ready-fg' },
  done: { dot: 'bg-stage-done-dot', pill: 'bg-stage-done-bg text-stage-done-fg' },
  interview: {
    dot: 'bg-stage-interview-dot',
    pill: 'bg-stage-interview-bg text-stage-interview-fg',
  },
  closed: { dot: 'bg-stage-closed-dot', pill: 'bg-stage-closed-bg text-stage-closed-fg' },
}

export function StageDot({ stage, className }: { stage: Stage; className?: string }) {
  return <span className={cn('size-2 shrink-0 rounded-full', STAGE_CLASSES[stage].dot, className)} />
}

export function StageBadge({
  stage,
  label,
  className,
}: {
  stage: Stage
  label: string
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex h-5 shrink-0 items-center gap-1.5 rounded-sm px-1.5 text-xs font-medium whitespace-nowrap',
        STAGE_CLASSES[stage].pill,
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', STAGE_CLASSES[stage].dot)} />
      {label}
    </span>
  )
}

const FIT_CLASSES: Record<FitBand, string> = {
  strong: 'bg-fit-strong-bg text-fit-strong-fg border-fit-strong-border',
  good: 'bg-fit-good-bg text-fit-good-fg border-fit-good-border',
  fair: 'bg-fit-fair-bg text-fit-fair-fg border-fit-fair-border',
  weak: 'bg-fit-weak-bg text-fit-weak-fg border-fit-weak-border',
  failed: 'bg-danger-bg text-danger-fg border-tone-red-border',
  pending: 'border-dashed border-border-strong text-fg-subtle',
}

const FIT_LABELS: Record<FitBand, string> = {
  strong: 'Strong fit (80+)',
  good: 'Good fit (65–79)',
  fair: 'Fair fit (50–64)',
  weak: 'Weak fit (<50)',
  failed: 'Scoring failed. Open the job to see why and retry.',
  pending: 'Not scored yet (queued)',
}

const CONFIDENCE_TEXT: Record<Confidence, string> = {
  high: 'Scored on the full listing',
  medium: 'Scored on a summary of the listing',
  low: 'Scored on a short snippet',
}

const SIZE = {
  lg: 'h-10 min-w-12 px-2 text-md',
  md: 'h-6 min-w-9 px-1.5 text-xs',
  sm: 'h-5 min-w-7 px-1 text-2xs',
}

/**
 * Fit score pill. `detailed` adds the confidence mark (Med/Low), a hard red-flag marker and a
 * stale marker next to the number.
 */
export function FitBadge({
  fit,
  size = 'md',
  detailed = false,
  hidden = false,
  className,
}: {
  fit: FitBrief | null
  size?: 'sm' | 'md' | 'lg'
  detailed?: boolean
  /** Blind labeling: show a neutral placeholder instead of the score, band and flags. */
  hidden?: boolean
  className?: string
}) {
  if (hidden) {
    return (
      <Tooltip content="Score hidden while you label (toggle in Discover)">
        <span
          className={cn(
            'inline-flex shrink-0 items-center justify-center rounded-md border border-dashed border-border-strong text-fg-subtle',
            SIZE[size],
            className,
          )}
          aria-label="Score hidden"
        >
          <EyeOff className={size === 'lg' ? 'size-4' : 'size-3'} />
        </span>
      </Tooltip>
    )
  }
  const band: FitBand = fit?.band ?? 'pending'
  const pill = (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-md border font-semibold tabular-nums',
        FIT_CLASSES[band],
        SIZE[size],
        className,
      )}
    >
      {band === 'failed' ? (
        <CircleAlert className={size === 'lg' ? 'size-4' : 'size-3'} />
      ) : fit?.score == null ? (
        <CircleDashed className={size === 'lg' ? 'size-4' : 'size-3'} />
      ) : (
        fit.score
      )}
    </span>
  )
  const tip = (
    <span className="block space-y-0.5">
      <span className="block">{FIT_LABELS[band]}</span>
      {fit?.status === 'ok' && <span className="block text-fg-muted">{CONFIDENCE_TEXT[fit.confidence]}</span>}
      {fit?.hard_flag && <span className="block text-danger-fg">Has a disqualifying red flag (score capped)</span>}
      {fit?.stale && <span className="block text-warning-fg">Stale: your experience changed since scoring</span>}
      {fit?.model && (
        <span className="block font-mono text-2xs text-fg-subtle">
          {fit.model}
          {fit.prompt_version ? ` · ${fit.prompt_version.replace('fit_score/', 'prompt ')}` : ''}
        </span>
      )}
    </span>
  )
  if (!detailed) return <Tooltip content={tip}>{pill}</Tooltip>
  return (
    <Tooltip content={tip}>
      <span className="inline-flex shrink-0 items-center gap-1">
        {pill}
        {fit?.status === 'ok' && fit.confidence !== 'high' && (
          <span className="text-2xs font-medium text-fg-subtle">{fit.confidence === 'medium' ? 'Med' : 'Low'}</span>
        )}
        {fit?.hard_flag && <Flag className="size-3.5 text-danger-dot" aria-label="Disqualifying red flag" />}
        {fit?.stale && <span className="size-1.5 rounded-full bg-warning-dot" aria-label="Stale score" />}
      </span>
    </Tooltip>
  )
}

const LABEL_TONE: Record<UserLabel, Tone> = { good: 'green', maybe: 'amber', no: 'gray' }
const LABEL_TEXT: Record<UserLabel, string> = { good: 'Good', maybe: 'Maybe', no: 'No' }

/** Your Good / Maybe / No judgment (used to evaluate the scorer). */
export function LabelBadge({ label }: { label: UserLabel | null }) {
  if (!label) return null
  return (
    <ToneBadge tone={LABEL_TONE[label]} dot={false} className="h-4.5 px-1 text-2xs">
      {LABEL_TEXT[label]}
    </ToneBadge>
  )
}

export function SourceBadge({ source, short = true }: { source: Source; short?: boolean }) {
  return (
    <Tooltip content={short ? SOURCE_LABELS[source] : null}>
      <span className="inline-flex h-5 shrink-0 items-center rounded-sm border border-border bg-bg-subtle px-1.5 text-xs text-fg-muted">
        {short ? SOURCE_SHORT[source] : SOURCE_LABELS[source]}
      </span>
    </Tooltip>
  )
}

export function RemoteBadge({ remote }: { remote: RemoteType }) {
  if (remote === 'unknown') return null
  const tone: Tone = remote === 'remote' ? 'teal' : remote === 'hybrid' ? 'slate' : 'gray'
  return (
    <ToneBadge tone={tone} dot={false}>
      {REMOTE_LABELS[remote]}
    </ToneBadge>
  )
}

export function LocationText({ location, className }: { location: string; className?: string }) {
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-1 text-fg-muted', className)}>
      <MapPin className="size-3.5 shrink-0 text-fg-subtle" />
      <span className="truncate">{location}</span>
    </span>
  )
}

const TIER_TONE: Record<ContactTier, Tone> = {
  apollo_dump: 'green',
  lookup_found: 'green',
  lookup_queued: 'amber',
  none: 'gray',
}

export function ContactTierBadge({ tier }: { tier: ContactTier }) {
  const Icon =
    tier === 'none' ? UserRoundX : tier === 'lookup_queued' ? SearchIcon : UserRoundCheck
  return (
    <ToneBadge tone={TIER_TONE[tier]} dot={false}>
      <Icon className="size-3.5" />
      {TIER_LABELS[tier]}
    </ToneBadge>
  )
}

const APPLICATION_TRACK: Record<ApplicationTrack, { label: string; tone: Tone }> = {
  not_ready: { label: 'CV first', tone: 'gray' },
  ready: { label: 'Ready to apply', tone: 'amber' },
  applied: { label: 'Applied', tone: 'green' },
}
const OUTREACH_TRACK: Record<OutreachTrack, { label: string; tone: Tone }> = {
  no_contact: { label: 'No contact', tone: 'gray' },
  contact: { label: 'Contact found', tone: 'slate' },
  drafted: { label: 'Draft to review', tone: 'amber' },
  approved: { label: 'Approved', tone: 'blue' },
  queued: { label: 'Queued', tone: 'violet' },
  sent: { label: 'Sent', tone: 'green' },
}

/** One route's status: "Apply · Ready to apply" or "Email · Draft to review". */
export function TrackBadge({ kind, tracks, className }: { kind: 'application' | 'outreach'; tracks: Tracks; className?: string }) {
  const item = kind === 'application' ? APPLICATION_TRACK[tracks.application] : OUTREACH_TRACK[tracks.outreach]
  const Icon = kind === 'application' ? Globe : Mail
  return (
    <Tooltip content={kind === 'application' ? 'Web application' : `Cold email${tracks.contact_name ? ` to ${tracks.contact_name}` : ''}`}>
      <span>
        <ToneBadge tone={item.tone} dot={false} className={className}>
          <Icon className="size-3.5" />
          {item.label}
        </ToneBadge>
      </span>
    </Tooltip>
  )
}

/** Both routes side by side (web application + cold email). */
export function TrackBadges({ tracks, className }: { tracks: Tracks; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1', className)}>
      <TrackBadge kind="application" tracks={tracks} />
      <TrackBadge kind="outreach" tracks={tracks} />
    </span>
  )
}
