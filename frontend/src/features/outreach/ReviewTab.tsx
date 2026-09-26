import { CircleCheck, FileText, Inbox, Mail, RefreshCw, RotateCcw, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { FitBadge, ToneBadge, type Tone } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Kbd } from '@/components/ui/kbd'
import { Label } from '@/components/ui/label'
import { SegmentedList, SegmentedTrigger, Tabs } from '@/components/ui/tabs'
import { useHotkeys } from '@/hooks/useHotkeys'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { relativeTime, shortAge } from '@/lib/format'
import { useDraftAction, useDrafts, useGenerateDraft, useSaveDraft } from '@/lib/queries/workflow'
import type { Draft, DraftStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

const STATUS: Record<DraftStatus, { tone: Tone; label: string }> = {
  draft: { tone: 'amber', label: 'Needs review' },
  approved: { tone: 'blue', label: 'Approved' },
  queued: { tone: 'blue', label: 'Queued' },
  sent: { tone: 'green', label: 'Sent' },
  rejected: { tone: 'gray', label: 'Rejected' },
  failed: { tone: 'red', label: 'Failed' },
}

function DraftEditor({
  draft,
  onApprove,
  onReject,
}: {
  draft: Draft
  onApprove: () => void
  onReject: () => void
}) {
  const save = useSaveDraft()
  const regenerate = useGenerateDraft()
  const action = useDraftAction()
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const timer = useRef<number | undefined>(undefined)
  const editable = draft.status === 'draft'

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const queueSave = (next: { subject?: string; body?: string }) => {
    setSaveState('saving')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      save.mutate(
        { id: draft.id, ...next },
        {
          onSuccess: () => setSaveState('saved'),
          onError: (e) => {
            setSaveState('idle')
            toast.error(`Couldn't save: ${e.message}`)
          },
        },
      )
    }, 700)
  }

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-border px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-md font-semibold tracking-tight">
              {draft.contact ? `To ${draft.contact.full_name}` : 'No recipient'}
            </p>
            <p className="truncate text-sm text-fg-muted">
              {draft.contact?.title} · {draft.contact?.email}
            </p>
          </div>
          <ToneBadge tone={STATUS[draft.status].tone}>{STATUS[draft.status].label}</ToneBadge>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
          <Link
            to={`/jobs/${draft.job_id}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-subtle px-2 py-1 hover:border-border-strong"
          >
            <FitBadge fit={draft.fit} size="sm" />
            <span className="font-medium text-fg">{draft.job_title}</span>
            <span>· {draft.company_name}</span>
          </Link>
          {draft.cv_version && (
            <Link
              to={`/jobs/${draft.job_id}/cv`}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-subtle px-2 py-1 hover:border-border-strong"
            >
              <FileText className="size-3.5" />
              CV v{draft.cv_version} attached
            </Link>
          )}
          <span className="ml-auto">
            {draft.edited ? 'Edited by you · ' : ''}Drafted by {draft.model} · {relativeTime(draft.created_at)}
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5">
        <div className="space-y-1.5">
          <Label htmlFor="subject">Subject</Label>
          <Input
            id="subject"
            value={subject}
            readOnly={!editable}
            onChange={(e) => {
              setSubject(e.target.value)
              queueSave({ subject: e.target.value })
            }}
            className="h-9 text-base font-medium"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="body">Message</Label>
          <Textarea
            id="body"
            value={body}
            readOnly={!editable}
            onChange={(e) => {
              setBody(e.target.value)
              queueSave({ body: e.target.value })
            }}
            className="field-sizing-content min-h-72 text-base leading-7"
          />
        </div>
      </div>

      <div className="flex h-14 shrink-0 items-center gap-2 border-t border-border px-6">
        <span className="text-xs text-fg-subtle">
          {editable
            ? saveState === 'saving'
              ? 'Saving…'
              : saveState === 'saved'
                ? 'All changes saved'
                : 'Edits autosave'
            : draft.status === 'rejected'
              ? 'Rejected drafts are kept for reference'
              : 'This email has left review'}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {editable && (
            <>
              <Button variant="ghost" onClick={onReject}>
                <X />
                Reject
                <Kbd>R</Kbd>
              </Button>
              <Button
                onClick={() =>
                  regenerate.mutate(draft.application_id, {
                    onSuccess: () => toast.success('New draft generated'),
                    onError: (e) => toast.error(e.message),
                  })
                }
                disabled={regenerate.isPending}
              >
                <RefreshCw className={regenerate.isPending ? 'animate-spin' : undefined} />
                Regenerate
              </Button>
              <Button variant="default" onClick={onApprove}>
                <CircleCheck />
                Approve & queue
                <Kbd className="border-transparent bg-primary-hover text-primary-fg">A</Kbd>
              </Button>
            </>
          )}
          {draft.status === 'rejected' && (
            <Button
              onClick={() =>
                action.mutate(
                  { id: draft.id, action: 'restore' },
                  { onSuccess: () => toast.success('Moved back to review') },
                )
              }
            >
              <RotateCcw />
              Restore to review
            </Button>
          )}
          {(draft.status === 'queued' || draft.status === 'sent') && (
            <Button asChild>
              <Link to="/outreach?tab=queue">
                <Mail />
                View send queue
              </Link>
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

export function ReviewTab() {
  const url = useSearchParamState()
  const status = url.get('status') ?? 'draft'
  const selectedId = url.get('draft') ? Number(url.get('draft')) : null
  const { data, isPending, error, refetch } = useDrafts(status)
  const action = useDraftAction()

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
            toast.success(d.status === 'queued' ? 'Approved and queued' : 'Approved (queue is full)', {
              description: `To ${d.contact?.full_name} · ${d.company_name}`,
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
      <div className="flex w-[360px] shrink-0 flex-col border-r border-border bg-bg max-xl:w-[300px]">
        <div className="border-b border-border px-4 py-2.5">
          <Tabs value={status} onValueChange={(v) => url.set({ status: v === 'draft' ? null : v, draft: null })}>
            <SegmentedList className="w-full">
              <SegmentedTrigger value="draft" className="flex-1 justify-center">To review</SegmentedTrigger>
              <SegmentedTrigger value="approved" className="flex-1 justify-center">Approved</SegmentedTrigger>
              <SegmentedTrigger value="rejected" className="flex-1 justify-center">Rejected</SegmentedTrigger>
              <SegmentedTrigger value="all" className="flex-1 justify-center">All</SegmentedTrigger>
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
              action={
                status === 'draft' && (
                  <Button size="sm" asChild>
                    <Link to="/pipeline">Open pipeline</Link>
                  </Button>
                )
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
                {status !== 'draft' && (
                  <ToneBadge tone={STATUS[d.status].tone} className="mt-1.5">
                    {STATUS[d.status].label}
                  </ToneBadge>
                )}
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
      <div className="min-w-0 flex-1 bg-surface">
        {selected ? (
          <DraftEditor
            key={selected.id}
            draft={selected}
            onApprove={() => decide(selected, 'approve')}
            onReject={() => decide(selected, 'reject')}
          />
        ) : (
          !isPending &&
          !error && (
            <EmptyState
              icon={Mail}
              title="Select a draft"
              description="Every email is reviewed here before it can be queued."
            />
          )
        )}
      </div>
    </div>
  )
}
