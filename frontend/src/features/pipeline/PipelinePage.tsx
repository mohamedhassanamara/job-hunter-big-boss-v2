import { Columns3, Compass, Rows3, Search, SearchX } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { CloseDialog } from '@/components/app/CloseDialog'
import { PageHeader } from '@/components/app/PageHeader'
import { EmptyState, ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { SegmentedList, SegmentedTrigger, Tabs } from '@/components/ui/tabs'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useTriageActions } from '@/hooks/useTriageActions'
import { COLUMN_LABELS, pluralize } from '@/lib/format'
import { useApplications, usePatchApplication } from '@/lib/queries/jobs'
import type { CloseReason, PipelineCard, Stage } from '@/lib/types'
import { Board } from './Board'
import { Table } from './Table'

function BoardSkeleton() {
  return (
    <div className="flex gap-3 px-6 py-4" aria-busy="true">
      {Array.from({ length: 7 }, (_, i) => (
        <div key={i} className="w-64 shrink-0 space-y-2 rounded-lg bg-bg-subtle p-2">
          <Skeleton className="h-6 w-24" />
          {Array.from({ length: (i % 3) + 1 }, (_, j) => (
            <Skeleton key={j} className="h-24" />
          ))}
        </div>
      ))}
    </div>
  )
}

export default function PipelinePage() {
  const url = useSearchParamState()
  const view = url.get('view') === 'table' ? 'table' : 'board'
  const showDismissed = url.get('dismissed') === '1'
  const [q, setQ] = useState('')
  const [closing, setClosing] = useState<PipelineCard | null>(null)
  const { data, isPending, error, refetch } = useApplications()
  const patch = usePatchApplication()
  const triage = useTriageActions()

  const cards = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (data ?? []).filter(
      (c) =>
        (showDismissed || c.close_reason !== 'dismissed') &&
        (!needle || c.title.toLowerCase().includes(needle) || c.company_name.toLowerCase().includes(needle)),
    )
  }, [data, q, showDismissed])

  const active = (data ?? []).filter((c) => c.stage !== 'new' && c.stage !== 'closed').length

  const move = (card: PipelineCard, to: Stage, close_reason?: CloseReason) => {
    if (!card.allowed_stages.includes(to)) {
      toast.error(`Can't move to ${COLUMN_LABELS[to]}`, {
        description: `From ${card.stage_label}, a job can go to: ${card.allowed_stages.map((s) => COLUMN_LABELS[s]).join(', ')}.`,
      })
      return
    }
    if (to === 'closed' && !close_reason) {
      setClosing(card)
      return
    }
    const from = card.stage
    patch.mutate(
      { id: card.application_id, patch: { stage: to, close_reason } },
      {
        onSuccess: (updated) =>
          toast.success(`Moved to ${updated.stage_label}`, {
            description: card.title,
            duration: 8000,
            action: updated.allowed_stages.includes(from)
              ? {
                  label: 'Undo',
                  onClick: () => patch.mutate({ id: card.application_id, patch: { stage: from } }),
                }
              : undefined,
          }),
        onError: (e) => toast.error(e.message),
      },
    )
  }

  const target = (c: PipelineCard) => ({ jobId: c.job_id, title: c.title, company: c.company_name })

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Pipeline"
        description={data ? `${pluralize(active, 'active application')} · ${view === 'board' ? 'drag cards to move them' : 'click a column to sort'}` : 'Everything you are pursuing'}
        actions={
          <Tabs value={view} onValueChange={(v) => url.set({ view: v === 'board' ? null : v })}>
            <SegmentedList>
              <SegmentedTrigger value="board">
                <Columns3 />
                Board
              </SegmentedTrigger>
              <SegmentedTrigger value="table">
                <Rows3 />
                Table
              </SegmentedTrigger>
            </SegmentedList>
          </Tabs>
        }
      />
      <div className="flex items-center gap-3 border-b border-border bg-bg px-6 py-2.5">
        <div className="relative w-64">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-fg-subtle" />
          <Input
            data-page-search
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && e.currentTarget.blur()}
            placeholder="Filter by title or company"
            className="h-7 pl-8"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-fg-muted">
          <Switch checked={showDismissed} onCheckedChange={(v) => url.set({ dismissed: v ? '1' : null })} />
          Show dismissed
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {isPending ? (
          <BoardSkeleton />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : (data ?? []).length === 0 ? (
          <EmptyState
            icon={Compass}
            title="Nothing in your pipeline yet"
            description="Shortlist jobs from Discover and they'll show up here."
            action={
              <Button asChild size="sm" variant="default">
                <Link to="/discover">Go to Discover</Link>
              </Button>
            }
          />
        ) : cards.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No applications match"
            action={<Button size="sm" onClick={() => setQ('')}>Clear filter</Button>}
          />
        ) : view === 'board' ? (
          <Board cards={cards} onMove={(c, to) => move(c, to)} />
        ) : (
          <Table
            cards={cards}
            onShortlist={(c) => triage.shortlist(target(c))}
            onDismiss={(c) => (c.stage === 'new' ? triage.dismiss(target(c)) : setClosing(c))}
          />
        )}
      </div>
      <CloseDialog
        key={closing?.application_id}
        open={!!closing}
        title={closing ? `${closing.title} · ${closing.company_name}` : ''}
        onCancel={() => setClosing(null)}
        onConfirm={(reason) => {
          if (closing) move(closing, 'closed', reason)
          setClosing(null)
        }}
      />
    </div>
  )
}
