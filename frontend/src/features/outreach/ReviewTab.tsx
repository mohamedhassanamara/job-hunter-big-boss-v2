import { Inbox, Mail } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { SegmentedList, SegmentedTrigger, Tabs } from '@/components/ui/tabs'
import { useHotkeys } from '@/hooks/useHotkeys'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { shortAge } from '@/lib/format'
import { useDraftAction, useDrafts, useQueueDraft } from '@/lib/queries/workflow'
import { DraftEditor } from '@/components/app/outreach/DraftEditor'
import { DRAFT_STATUS } from '@/lib/outreach'
import type { Draft } from '@/lib/types'
import { cn } from '@/lib/utils'

/** The claim check, done in the background after the draft is written: Approve doesn't wait. */
function VerifyChip({ state, errors }: { state: string; errors: boolean }) {
  if (errors) return <ToneBadge tone="amber">Fix the checks first</ToneBadge>
  if (state === 'passed') return <ToneBadge tone="green">Verified</ToneBadge>
  if (state === 'failed') return <ToneBadge tone="red">Claims failed</ToneBadge>
  if (state === 'stale') return <ToneBadge tone="amber">Re-checking</ToneBadge>
  if (state === 'error') return <ToneBadge tone="gray">Check didn't run</ToneBadge>
  return <ToneBadge tone="gray">Not verified yet</ToneBadge>
}

export function ReviewTab() {
  const url = useSearchParamState()
  const status = url.get('status') ?? 'draft'
  const selectedId = url.get('draft') ? Number(url.get('draft')) : null
  const { data, isPending, error, refetch } = useDrafts(status)
  const action = useDraftAction()
  const queueDraft = useQueueDraft()

  const drafts = useMemo(() => data ?? [], [data])
  const ids = useMemo(() => drafts.map((d) => d.id), [drafts])
  const selected = drafts.find((d) => d.id === selectedId) ?? drafts[0]

  // Keep the URL in sync with the implicit first selection.
  useEffect(() => {
    if (!selectedId && drafts[0]) url.set({ draft: drafts[0].id })
  }, [selectedId, drafts, url])

  const select = (id: number) => url.set({ draft: id })

  const decide = (draft: Draft, verdict: 'approve' | 'reject') => {
    if (draft.status !== 'draft') return
    const index = ids.indexOf(draft.id)
    const next = ids[index + 1] ?? ids[index - 1] ?? null
    action.mutate(
      { id: draft.id, action: verdict },
      {
        onSuccess: (d) => {
          if (status === 'draft') url.set({ draft: next })
          if (verdict === 'approve') {
            toast.success('Approved: ready to send', {
              description: `To ${d.contact?.full_name} · ${d.company_name}`,
              action: {
                label: 'Add to queue',
                onClick: () =>
                  queueDraft.mutate(d.id, {
                    onSuccess: () => toast.success('Added to the send queue'),
                    onError: (e) => toast.error(e.message),
                  }),
              },
            })
          } else {
            toast('Draft rejected', {
              description: `To ${d.contact?.full_name} · ${d.company_name}`,
              duration: 8000,
              action: {
                label: 'Undo',
                onClick: () =>
                  action.mutate(
                    { id: d.id, action: 'restore' },
                    { onSuccess: () => url.set({ draft: d.id }) },
                  ),
              },
            })
          }
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }

  useListKeyboard({ ids, selectedId: selected?.id ?? null, onSelect: select })
  useHotkeys({
    a: () => selected && decide(selected, 'approve'),
    r: () => selected && decide(selected, 'reject'),
  })

  return (
    <div className="flex h-full min-h-0">
      <div data-tour="outreach-list" className="flex w-[360px] shrink-0 flex-col border-r border-border bg-bg max-xl:w-[300px]">
        <div className="border-b border-border px-4 py-2.5">
          <Tabs value={status} onValueChange={(v) => url.set({ status: v === 'draft' ? null : v, draft: null })}>
            <SegmentedList className="w-full">
              <SegmentedTrigger value="draft" className="flex-1 justify-center px-1.5">To review</SegmentedTrigger>
              <SegmentedTrigger value="approved" className="flex-1 justify-center px-1.5">Approved</SegmentedTrigger>
              <SegmentedTrigger value="rejected" className="flex-1 justify-center px-1.5">Rejected</SegmentedTrigger>
              <SegmentedTrigger value="all" className="flex-1 justify-center px-1.5">All</SegmentedTrigger>
            </SegmentedList>
          </Tabs>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isPending ? (
            <SkeletonRows rows={5} />
          ) : error ? (
            <ErrorState compact error={error} onRetry={() => refetch()} />
          ) : drafts.length === 0 ? (
            <EmptyState
              compact
              icon={Inbox}
              title={status === 'draft' ? 'No drafts waiting' : 'Nothing here'}
              description={
                status === 'draft'
                  ? 'Drafts appear after you approve a CV for a job with a contact.'
                  : undefined
              }
            />
          ) : (
            drafts.map((d) => (
              <button
                key={d.id}
                data-row-id={d.id}
                onClick={() => select(d.id)}
                className={cn(
                  'relative block w-full border-b border-border px-4 py-3 text-left transition-colors duration-120',
                  selected?.id === d.id ? 'bg-surface-selected' : 'hover:bg-surface-hover',
                )}
              >
                {selected?.id === d.id && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
                <div className="flex items-center gap-2">
                  <span className="flex-1 truncate text-sm font-medium">
                    {d.contact?.full_name ?? 'No recipient'}
                  </span>
                  <span className="text-xs text-fg-subtle tabular-nums">{shortAge(d.created_at)}</span>
                </div>
                <p className="truncate text-xs text-fg-muted">
                  {d.company_name} · {d.job_title}
                </p>
                <p className="mt-1 truncate text-xs text-fg-subtle">{d.subject}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  {status !== 'draft' && <ToneBadge tone={DRAFT_STATUS[d.status].tone}>{DRAFT_STATUS[d.status].label}</ToneBadge>}
                  {d.status === 'draft' && <VerifyChip state={d.verification_state} errors={d.violations.some((v) => v.severity === 'error')} />}
                </div>
              </button>
            ))
          )}
        </div>
        {drafts.length > 0 && status === 'draft' && (
          <p className="border-t border-border px-4 py-2 text-2xs text-fg-subtle">
            J/K to move · A approve · R reject
          </p>
        )}
      </div>
      <div data-tour="outreach-editor" className="min-w-0 flex-1 bg-surface">
        {selected ? (
          <DraftEditor
            key={selected.id}
            draft={selected}
            onApprove={() => decide(selected, 'approve')}
            approving={action.isPending && action.variables?.action === 'approve'}
            onReject={() => decide(selected, 'reject')}
          />
        ) : (
          !isPending &&
          !error && (
            <EmptyState
              icon={Mail}
              title={status === 'draft' ? 'Nothing to review' : 'No drafts in this view'}
              description="Emails are drafted once a CV is approved for a job with a contact. Approved emails wait in the send queue."
              action={
                <div className="flex gap-2">
                  <Button size="sm" asChild>
                    <Link to="/pipeline">Open pipeline</Link>
                  </Button>
                  <TourButton tour="outreach" />
                </div>
              }
            />
          )
        )}
      </div>
    </div>
  )
}
