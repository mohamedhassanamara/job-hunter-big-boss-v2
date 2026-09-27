import { Copy, Star, UserRoundCheck, X } from 'lucide-react'
import { FitBadge, LabelBadge, RemoteBadge, SourceBadge, StageBadge } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Tooltip } from '@/components/ui/tooltip'
import { absoluteDate, shortAge } from '@/lib/format'
import type { JobListItem } from '@/lib/types'
import { cn } from '@/lib/utils'

export function JobRow({
  job,
  selected,
  onSelect,
  onShortlist,
  onDismiss,
  hideScore = false,
}: {
  job: JobListItem
  selected: boolean
  onSelect: () => void
  onShortlist: () => void
  onDismiss: () => void
  hideScore?: boolean
}) {
  const isNew = job.application.stage === 'new'
  const posted = job.posted_at ?? job.discovered_at
  return (
    <div
      data-row-id={job.id}
      role="option"
      aria-selected={selected}
      onClick={onSelect}
      className={cn(
        'group relative flex cursor-default items-center gap-3 border-b border-border px-6 py-2.5 transition-colors duration-120',
        selected ? 'bg-surface-selected' : 'hover:bg-surface-hover',
      )}
    >
      {selected && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
      <FitBadge fit={job.fit} detailed hidden={hideScore} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-fg">{job.title}</span>
          {job.duplicate_of_id && (
            <Tooltip content="Duplicate: same job listed on another source">
              <Copy className="size-3.5 shrink-0 text-warning-dot" />
            </Tooltip>
          )}
          <LabelBadge label={job.user_label} />
          {job.company_contacted && (
            <Tooltip content={`Already contacted ${job.company.name}`}>
              <UserRoundCheck className="size-3.5 shrink-0 text-warning-dot" />
            </Tooltip>
          )}
        </div>
        <div className="flex min-w-0 items-center gap-1.5 text-xs text-fg-muted">
          <span className="truncate font-medium">{job.company.name}</span>
          <span className="text-fg-subtle">·</span>
          <span className="truncate">{job.location}</span>
        </div>
      </div>
      {!isNew && <StageBadge stage={job.application.stage} label={job.application.stage_label} />}
      <div className="hidden items-center gap-1.5 lg:flex">
        <RemoteBadge remote={job.remote_type} />
        <SourceBadge source={job.source} />
      </div>
      <Tooltip content={`Posted ${absoluteDate(posted)}`}>
        <span className="w-8 text-right text-xs text-fg-subtle tabular-nums">{shortAge(posted)}</span>
      </Tooltip>
      {isNew && (
        <div className="absolute top-1/2 right-16 hidden -translate-y-1/2 items-center gap-1 rounded-md border border-border bg-surface-raised p-0.5 shadow-sm group-hover:flex">
          <Tooltip content={<span className="flex items-center gap-1.5">Shortlist <Kbd>S</Kbd></span>}>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Shortlist"
              onClick={(e) => {
                e.stopPropagation()
                onShortlist()
              }}
            >
              <Star />
            </Button>
          </Tooltip>
          <Tooltip content={<span className="flex items-center gap-1.5">Dismiss <Kbd>D</Kbd></span>}>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Dismiss"
              onClick={(e) => {
                e.stopPropagation()
                onDismiss()
              }}
            >
              <X />
            </Button>
          </Tooltip>
        </div>
      )}
    </div>
  )
}
