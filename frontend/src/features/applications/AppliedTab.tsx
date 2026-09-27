import { CalendarClock, Maximize2, MessageSquareReply, SearchX, Send, X } from 'lucide-react'
import { useNavigate } from 'react-router'
import { Link } from 'react-router'
import { SourceBadge, StageBadge } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { AppliedFacts, TrackingActions } from '@/components/app/tracking/TrackingPanel'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { Timeline } from '@/features/job/Timeline'
import { useHotkeys } from '@/hooks/useHotkeys'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { countryName } from '@/lib/format'
import { useJob } from '@/lib/queries/jobs'
import { useTracked } from '@/lib/queries/tracking'
import { CLOSE_REASON_LABELS, shortDate } from '@/lib/tracking'
import type { TrackedApplication } from '@/lib/types'
import { cn } from '@/lib/utils'
import { useTrackingFilters } from './filters'
import { TrackingFilterBar } from './TrackingFilterBar'

function Row({ r, selected, onSelect }: { r: TrackedApplication; selected: boolean; onSelect: () => void }) {
  return (
    <div
      data-row-id={r.application_id}
      role="option"
      aria-selected={selected}
      onClick={onSelect}
      className={cn(
        'relative grid cursor-default grid-cols-[88px_minmax(0,1fr)_120px_88px_72px_120px] items-center gap-3 border-b border-border px-6 py-2.5 transition-colors duration-120',
        selected ? 'bg-surface-selected' : 'hover:bg-surface-hover',
      )}
    >
      {selected && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
      <span className="text-xs text-fg-muted tabular-nums">{shortDate(r.applied_at)}</span>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{r.title}</p>
        <p className="truncate text-xs text-fg-muted">
          {r.company} · {r.track ?? 'No track'} · {r.country ? countryName(r.country) : 'Remote'}
        </p>
      </div>
      <span className="truncate">
        <StageBadge stage={r.stage} label={r.close_reason && r.stage === 'closed' ? CLOSE_REASON_LABELS[r.close_reason] : r.stage_label} />
      </span>
      <SourceBadge source={r.source} />
      <span className="flex items-center gap-2 text-xs text-fg-muted tabular-nums">
        <Tooltip content="Replies">
          <span className="inline-flex items-center gap-0.5">
            <MessageSquareReply className="size-3.5 text-fg-subtle" />
            {r.responses.length}
          </span>
        </Tooltip>
        <Tooltip content="Interview rounds">
          <span className="inline-flex items-center gap-0.5">
            <CalendarClock className="size-3.5 text-fg-subtle" />
            {r.interviews.length}
          </span>
        </Tooltip>
      </span>
      <span className="text-right text-xs text-fg-subtle">
        {r.days_to_first_response !== null ? `answer in ${Math.round(r.days_to_first_response)}d` : 'no answer yet'}
      </span>
    </div>
  )
}

function Panel({ r, onClose }: { r: TrackedApplication; onClose: () => void }) {
  const job = useJob(r.job_id)
  return (
    <aside data-tour="applications-panel" className="flex h-full w-[440px] shrink-0 flex-col border-l border-border bg-surface max-xl:w-[380px]">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border px-4">
        <span className="text-xs text-fg-subtle">
          <Kbd>J</Kbd> <Kbd>K</Kbd> to move · <Kbd>Esc</Kbd> to close
        </span>
        <div className="flex items-center gap-0.5">
          <Tooltip content={<span className="flex items-center gap-1.5">Open job page <Kbd>↵</Kbd></span>}>
            <Button size="icon-sm" variant="ghost" asChild>
              <Link to={`/jobs/${r.job_id}`} aria-label="Open job page">
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
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
        <div className="space-y-1">
          <h2 className="text-md font-semibold tracking-tight">{r.title}</h2>
          <p className="text-sm text-fg-muted">{r.company}</p>
        </div>
        <TrackingActions
          target={{ appId: r.application_id, title: r.title, company: r.company }}
          stage={r.stage}
          rounds={r.interviews.length}
        />
        <div className="rounded-lg border border-border">
          <AppliedFacts tracking={r} />
        </div>
        {job.isPending ? (
          <Skeleton className="h-40" />
        ) : job.error ? (
          <ErrorState error={job.error} onRetry={() => job.refetch()} />
        ) : (
          <Timeline events={job.data.events} />
        )}
      </div>
    </aside>
  )
}

export function AppliedTab() {
  const url = useSearchParamState()
  const navigate = useNavigate()
  const { filters, active, clear } = useTrackingFilters()
  const { data, isPending, error, refetch } = useTracked(filters)
  const rows = data ?? []
  const selectedId = Number(url.get('app')) || null
  const selected = rows.find((r) => r.application_id === selectedId) ?? null
  const select = (id: number | null) => url.set({ app: id })

  useListKeyboard({
    ids: rows.map((r) => r.application_id),
    selectedId,
    onSelect: (id) => select(id),
    onOpen: (id) => {
      const r = rows.find((x) => x.application_id === id)
      if (r) navigate(`/jobs/${r.job_id}`)
    },
  })
  useHotkeys({ escape: () => select(null) }, { enabled: selectedId !== null })

  return (
    <>
      <TrackingFilterBar showExport />
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto" role="listbox" aria-label="Applied" data-tour="applications-list">
          {isPending ? (
            <SkeletonRows rows={8} />
          ) : error ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            active ? (
              <EmptyState
                icon={SearchX}
                title="No applications match these filters"
                action={<Button size="sm" onClick={clear}>Clear filters</Button>}
              />
            ) : (
              <EmptyState
                icon={Send}
                title="No applications yet"
                description="Mark a job applied from Ready to apply (or send a cold email) and it shows up here with its replies and interviews."
                action={
                  <div className="flex gap-2">
                    <Button size="sm" variant="default" onClick={() => url.set({ tab: null })}>
                      Go to Ready to apply
                    </Button>
                    <TourButton tour="applications" />
                  </div>
                }
              />
            )
          ) : (
            rows.map((r) => (
              <Row
                key={r.application_id}
                r={r}
                selected={r.application_id === selectedId}
                onSelect={() => select(r.application_id === selectedId ? null : r.application_id)}
              />
            ))
          )}
        </div>
        {selected && <Panel key={selected.application_id} r={selected} onClose={() => select(null)} />}
      </div>
    </>
  )
}
