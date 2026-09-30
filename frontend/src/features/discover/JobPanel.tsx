import { ArrowUpRight, EyeOff, Maximize2, Star, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import {
  LocationText,
  RemoteBadge,
  TrackBadges,
  SourceBadge,
  StageBadge,
} from '@/components/app/badges'
import { FitCard } from '@/components/app/FitCard'
import { ContactCard, ExternalListingButton, JobFlags } from '@/components/app/job-cards'
import { LabelPicker } from '@/components/app/LabelPicker'
import { Prose } from '@/components/app/Prose'
import { ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { absoluteDate, relativeTime, SOURCE_LABELS } from '@/lib/format'
import { useJob } from '@/lib/queries/jobs'
import type { UserLabel } from '@/lib/types'

export function JobPanel({
  jobId,
  onClose,
  onShortlist,
  onDismiss,
  onLabel,
  hideScores = false,
}: {
  jobId: number
  onClose: () => void
  onShortlist: () => void
  onDismiss: () => void
  onLabel: (label: UserLabel | null) => void
  hideScores?: boolean
}) {
  const { data: job, isPending, error, refetch } = useJob(jobId)
  const [reveal, setReveal] = useState(false)

  return (
    <aside data-tour="discover-panel" className="flex h-full w-[440px] shrink-0 flex-col border-l border-border bg-surface max-xl:w-[380px]">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border px-4">
        <span className="text-xs text-fg-subtle">
          <Kbd>J</Kbd> <Kbd>K</Kbd> to move · <Kbd>Esc</Kbd> to close
        </span>
        <div className="flex items-center gap-0.5">
          <Tooltip content={<span className="flex items-center gap-1.5">Open full page <Kbd>↵</Kbd></span>}>
            <Button size="icon-sm" variant="ghost" asChild>
              <Link to={`/jobs/${jobId}`} aria-label="Open full page">
                <Maximize2 />
              </Link>
            </Button>
          </Tooltip>
          <Tooltip content="Close">
            <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close panel">
              <X />
            </Button>
          </Tooltip>
        </div>
      </div>

      {isPending ? (
        <div className="space-y-4 p-5">
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div className="space-y-4 p-5">
            <div className="space-y-2">
              <h2 className="text-md leading-snug font-semibold tracking-tight">{job.title}</h2>
              <p className="text-sm font-medium text-fg-muted">{job.company.name}</p>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <LocationText location={job.location} />
                <RemoteBadge remote={job.remote_type} />
                <SourceBadge source={job.source} short={false} />
                {job.application.stage !== 'new' && <TrackBadges tracks={job.application.tracks} />}
              </div>
              <p className="text-xs text-fg-subtle">
                <Tooltip content={absoluteDate(job.posted_at)}>
                  <span>Posted {relativeTime(job.posted_at)}</span>
                </Tooltip>
                {job.salary_text && <> · {job.salary_text}</>}
              </p>
            </div>

            <div data-tour="discover-actions" className="flex flex-wrap items-center gap-2">
              {job.application.stage === 'new' ? (
                <>
                  <Button variant="default" size="sm" onClick={onShortlist}>
                    <Star />
                    Shortlist
                    <Kbd className="ml-1 border-transparent bg-primary-hover text-primary-fg">S</Kbd>
                  </Button>
                  <Button size="sm" onClick={onDismiss}>
                    <X />
                    Dismiss
                    <Kbd className="ml-1">D</Kbd>
                  </Button>
                </>
              ) : (
                <>
                  <StageBadge stage={job.application.stage} label={job.application.stage_label} />
                  <Button size="sm" variant="default" asChild>
                    <Link to={`/jobs/${job.id}`}>
                      Open job
                      <ArrowUpRight />
                    </Link>
                  </Button>
                </>
              )}
              <ExternalListingButton url={job.url} label={`Open on ${SOURCE_LABELS[job.source]}`} />
            </div>

            <div data-tour="discover-label" className="flex items-center justify-between gap-3 rounded-lg border border-border bg-bg-subtle px-3 py-2">
              <div>
                <p className="text-xs font-medium">Your label</p>
                <p className="text-2xs text-fg-subtle">Helps evaluate the scorer. Not a pipeline stage.</p>
              </div>
              <LabelPicker value={job.user_label} onChange={onLabel} />
            </div>
            <JobFlags job={job} />
            <div data-tour="discover-fit">
              {hideScores && !reveal ? (
                <div className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-border-strong px-3 py-2.5">
                  <p className="flex items-center gap-2 text-xs text-fg-muted">
                    <EyeOff className="size-3.5 text-fg-subtle" />
                    Fit score hidden while you label.
                  </p>
                  <Button size="xs" variant="ghost" onClick={() => setReveal(true)}>
                    Show for this job
                  </Button>
                </div>
              ) : (
                <FitCard job={job} />
              )}
            </div>
            <ContactCard job={job} />

            <div>
              <p className="mb-2 text-xs font-medium text-fg-subtle">Description</p>
              <Prose text={job.description} />
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
