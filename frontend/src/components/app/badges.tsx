import {
  CircleDashed,
  Globe,
  Mail,
  MapPin,
  Search as SearchIcon,
  UserRoundCheck,
  UserRoundX,
} from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'
import { REMOTE_LABELS, SOURCE_LABELS, SOURCE_SHORT, TIER_LABELS } from '@/lib/format'
import type { ContactTier, FitBand, FitBrief, RemoteType, Route, Source, Stage } from '@/lib/types'
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
}

const FIT_LABELS: Record<FitBand, string> = {
  strong: 'Strong fit (80+)',
  good: 'Good fit (65–79)',
  fair: 'Fair fit (50–64)',
  weak: 'Weak fit (<50)',
}

export function FitBadge({
  fit,
  size = 'md',
  className,
}: {
  fit: FitBrief | null
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  if (!fit) {
    return (
      <Tooltip content="Not scored yet">
        <span
          className={cn(
            'inline-flex items-center justify-center rounded-md border border-dashed border-border-strong text-fg-subtle',
            size === 'lg' ? 'h-10 w-12' : size === 'sm' ? 'h-5 w-7' : 'h-6 w-9',
            className,
          )}
        >
          <CircleDashed className="size-3" />
        </span>
      </Tooltip>
    )
  }
  return (
    <Tooltip content={FIT_LABELS[fit.band]}>
      <span
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded-md border font-semibold tabular-nums',
          FIT_CLASSES[fit.band],
          size === 'lg'
            ? 'h-10 w-12 text-md'
            : size === 'sm'
              ? 'h-5 min-w-7 px-1 text-2xs'
              : 'h-6 min-w-9 px-1.5 text-xs',
          className,
        )}
      >
        {fit.score}
      </span>
    </Tooltip>
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

export function RouteIcon({ route, className }: { route: Route; className?: string }) {
  if (route === 'undecided') return null
  const Icon = route === 'cold_email' ? Mail : Globe
  return (
    <Tooltip content={route === 'cold_email' ? 'Cold email' : 'Web apply'}>
      <Icon className={cn('size-3.5 shrink-0 text-fg-subtle', className)} />
    </Tooltip>
  )
}

export function RouteLabel({ route }: { route: Route }) {
  if (route === 'undecided') return <span className="text-fg-subtle">Undecided</span>
  const Icon = route === 'cold_email' ? Mail : Globe
  return (
    <span className="inline-flex items-center gap-1.5 text-fg-muted">
      <Icon className="size-3.5 text-fg-subtle" />
      {route === 'cold_email' ? 'Cold email' : 'Web apply'}
    </span>
  )
}
