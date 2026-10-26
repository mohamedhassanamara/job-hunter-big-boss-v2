import { CircleCheck, FileText, ListChecks, RefreshCw, SkipForward, SquarePen } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { PageHeader } from '@/components/app/PageHeader'
import { RegenerateDialog } from '@/components/app/RegenerateDialog'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Kbd } from '@/components/ui/kbd'
import { Skeleton } from '@/components/ui/skeleton'
import { useHotkeys } from '@/hooks/useHotkeys'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { ApiError } from '@/lib/api'
import { useApproveCV, useCVReview, useCVStudio, useGenerateCV, useRegenerateBatch, useRegenerateSummary, useRetryRegen } from '@/lib/queries/workflow'
import type { CVReviewRow } from '@/lib/types'
import { cn } from '@/lib/utils'
import { FitBadge, Workspace } from '../cv-studio/CVWorkspace'
import { approveGate } from '../cv-studio/cvGate'
import { LeftOutPopover } from './LeftOutPopover'
import { RegenerateSelectedDialog } from './RegenerateSelectedDialog'
import { useRowSelection } from './useRowSelection'

function CheckChip({ row }: { row: CVReviewRow }) {
  if (row.error) return <ToneBadge tone="red">LaTeX error</ToneBadge>
  if (row.page_count == null) return <ToneBadge tone="gray">Not compiled</ToneBadge>
  if (row.page_count !== 1) return <ToneBadge tone="red">{row.page_count} pages</ToneBadge>
  if (row.error_count > 0) return <ToneBadge tone="red">{row.error_count} error{row.error_count === 1 ? '' : 's'}</ToneBadge>
  return <ToneBadge tone="green">Ready to approve</ToneBadge>
}

/** The state of a row's "Regenerate selected" task; a failed one offers Retry (and Gemini for one call). */
function RegenChip({ row }: { row: CVReviewRow }) {
  const retry = useRetryRegen()
  const r = row.regen
  if (!r) return null
  if (r.status === 'queued') return <ToneBadge tone="gray">Regeneration queued</ToneBadge>
  if (r.status === 'running') return <ToneBadge tone="blue">Regenerating…</ToneBadge>
  if (r.status === 'done') return <ToneBadge tone="green">Regenerated</ToneBadge>
  if (r.status === 'skipped') return <ToneBadge tone="gray">Skipped: {r.warning}</ToneBadge>
  const go = (use?: 'gemini') => retry.mutate({ application_id: row.application_id, use }, { onError: (e) => toast.error(e.message) })
  return (
    <span className="flex flex-wrap items-center gap-1.5" title={r.error ?? undefined}>
      <ToneBadge tone="red">Regeneration failed</ToneBadge>
      <Button size="xs" variant="outline" disabled={retry.isPending} onClick={() => go()}>
        Retry
      </Button>
      <Button size="xs" variant="ghost" disabled={retry.isPending} onClick={() => go('gemini')}>
        Use Gemini
      </Button>
    </span>
  )
}

/** The CV drafts of your shortlisted jobs as one list: J/K move, A approves and goes to the next,
 * R regenerates with feedback (X ticks a row, Shift+R regenerates the ticked ones), E edits the summary, S skips. The approval rules are CV Studio's. */
export default function CVReviewPage() {
  const url = useSearchParamState()
  const { data, isPending, error, refetch } = useCVReview()
  const approve = useApproveCV()
  const generate = useGenerateCV()
  const regenSummary = useRegenerateSummary()
  const [regenerating, setRegenerating] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchKey, setBatchKey] = useState(0) // a fresh dialog (empty feedback) after each batch
  const batch = useRegenerateBatch()

  const rows = useMemo(() => data ?? [], [data])
  const ids = useMemo(() => rows.map((r) => r.application_id), [rows])
  const wanted = url.get('app') ? Number(url.get('app')) : null
  const selected = rows.find((r) => r.application_id === wanted) ?? rows[0]
  const select = useCallback((id: number) => url.set({ app: String(id) }), [url])
  const picks = useRowSelection(ids)
  const pickedRows = rows.filter((r) => picks.has(r.application_id))

  const studio = useCVStudio(selected?.application_id ?? NaN)
  const version = studio.data?.versions.find((v) => v.id === selected?.cv_id)
  // The live gate (a fresh edit changes it) falls back to the list's evaluation until it loads.
  const gate = version ? approveGate(version) : null
  const canApprove = gate ? gate.onePage && gate.errors.length === 0 && version?.status === 'draft' : Boolean(selected?.approvable)
  const blocked = gate
    ? !gate.onePage
      ? 'The CV must be exactly one page to approve'
      : gate.errors.length > 0
        ? `Fix ${gate.errors.length} problem${gate.errors.length > 1 ? 's' : ''} first: ${gate.errors[0].message}`
        : null
    : null

  const nextId = (id: number) => {
    const i = ids.indexOf(id)
    return ids[i + 1] ?? ids[i - 1] ?? null
  }

  const onApprove = (row: CVReviewRow) => {
    if (approve.isPending) return
    if (!canApprove || row.application_id !== selected?.application_id) {
      toast.error(blocked ?? 'This CV cannot be approved yet: fix its problems first')
      return
    }
    const next = nextId(row.application_id)
    approve.mutate(row.cv_id, {
      onSuccess: () => toast.success(`CV approved: ${row.job_title}`, { description: `${row.company_name} · ${ids.length - 1} left to review` }),
      onError: (e) => toast.error(e.message),
    })
    if (next !== null) select(next) // on to the next job right away; the list refreshes behind it
  }

  const onSkip = (id: number) => {
    const next = ids[ids.indexOf(id) + 1]
    if (next !== undefined) select(next)
    else toast('That was the last one', { description: 'Skipped CVs stay in the list.' })
  }

  const focusSummary = () => {
    const el = document.querySelector<HTMLTextAreaElement>('[data-cv-summary]')
    if (el) {
      el.focus()
      el.scrollIntoView({ block: 'center' })
    } else toast('The summary is not editable on this draft')
  }

  const regenerate = (feedback: string) => {
    if (!selected) return
    const fail = (e: Error) => toast.error(e instanceof ApiError && e.status === 503 ? `${e.message} Try again, or use CV Studio to pick another model.` : e.message)
    const done = () => setRegenerating(false)
    if (feedback) {
      regenSummary.mutate(
        { cvId: selected.cv_id, feedback },
        { onSuccess: () => { toast.success('Summary rewritten with your feedback'); done() }, onError: fail },
      )
    } else {
      generate.mutate(
        { appId: selected.application_id },
        { onSuccess: (v) => { toast.success(`CV v${v.version} ready for review`); select(selected.application_id); done() }, onError: fail },
      )
    }
  }

  const openBatch = () => {
    if (picks.selected.length === 0) toast('Tick the CVs to regenerate first', { description: 'X ticks the current row; shift-click a checkbox for a range.' })
    else setBatchOpen(true)
  }

  const submitBatch = (mode: 'whole' | 'summary', feedback: string, confirm: boolean) => {
    batch.mutate(
      { application_ids: picks.selected, mode, feedback: feedback || null, confirm },
      {
        onSuccess: (res) => {
          toast.success(`${res.queued} regeneration${res.queued === 1 ? '' : 's'} queued`, {
            description: [res.already_queued ? `${res.already_queued} already queued` : '', res.skipped.length ? `${res.skipped.length} not in the list` : ''].filter(Boolean).join(' · ') || 'Each result is a new draft.',
          })
          picks.selectNone()
          setBatchOpen(false)
          setBatchKey((k) => k + 1)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }

  // R regenerates this CV; Shift+R the ticked ones (the list's own keys can't see Shift).
  useHotkeys({ r: (e) => (e.shiftKey ? openBatch() : setRegenerating(true)) }, { enabled: !regenerating && !batchOpen })

  useListKeyboard({
    ids,
    selectedId: selected?.application_id ?? null,
    onSelect: select,
    actions: {
      a: (id) => {
        const row = rows.find((r) => r.application_id === id)
        if (row) onApprove(row)
      },
      x: (id) => picks.toggle(id),
      e: focusSummary,
      s: onSkip,
    },
    enabled: !regenerating && !batchOpen,
  })

  const busy = generate.isPending || regenSummary.isPending

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Review CVs"
        description="The CV drafts of your shortlisted jobs. Approve one after another; nothing is approved for you."
        actions={<TourButton tour="review-cvs" />}
      />
      <div className="flex min-h-0 flex-1">
        <div data-tour="review-cvs-list" className="flex w-[340px] shrink-0 flex-col border-r border-border bg-bg max-xl:w-[290px]">
          {rows.length > 0 && (
            <div data-tour="review-cvs-select" className="flex items-center gap-2 border-b border-border px-4 py-2 text-xs text-fg-muted">
              <span className="tabular-nums">{picks.selected.length} selected</span>
              <Button size="xs" variant="ghost" onClick={picks.selectAll}>
                Select all
              </Button>
              <Button size="xs" variant="ghost" onClick={picks.selectNone} disabled={picks.selected.length === 0}>
                Select none
              </Button>
              <Button size="xs" variant="outline" className="ml-auto" onClick={openBatch} disabled={picks.selected.length === 0}>
                <ListChecks />
                Regenerate selected <Kbd>⇧R</Kbd>
              </Button>
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-y-auto">
            {isPending ? (
              <SkeletonRows rows={6} />
            ) : error ? (
              <ErrorState compact error={error} onRetry={() => refetch()} />
            ) : rows.length === 0 ? (
              <EmptyState
                compact
                icon={FileText}
                title="No CVs waiting for review"
                description="Shortlist jobs in Discover: a CV draft is written in the background and appears here."
                action={
                  <div className="flex gap-2">
                    <Button size="sm" asChild>
                      <Link to="/discover">Open Discover</Link>
                    </Button>
                    <TourButton tour="review-cvs" />
                  </div>
                }
              />
            ) : (
              rows.map((r) => (
                <div
                  key={r.application_id}
                  data-row-id={r.application_id}
                  className={cn(
                    'relative border-b border-border transition-colors duration-120',
                    selected?.application_id === r.application_id ? 'bg-surface-selected' : 'hover:bg-surface-hover',
                  )}
                >
                  {selected?.application_id === r.application_id && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
                  <Checkbox
                    checked={picks.has(r.application_id)}
                    onClick={(e) => picks.toggle(r.application_id, e.shiftKey)}
                    aria-label={`Select ${r.job_title} at ${r.company_name}`}
                    className="absolute left-3.5 top-3.5 z-10"
                  />
                  <button onClick={() => select(r.application_id)} className="block w-full py-3 pb-1 pl-10 pr-4 text-left">
                    <p className="truncate text-sm font-medium">{r.job_title}</p>
                    <p className="truncate text-xs text-fg-muted">
                      {r.company_name}
                      {r.track ? ` · ${r.track}` : ''}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <CheckChip row={r} />
                      {r.fill != null && r.page_count === 1 && <span className="text-2xs text-fg-subtle tabular-nums">{Math.round(r.fill * 100)}% full</span>}
                      {r.summary_warnings > 0 && <ToneBadge tone="amber">{r.summary_warnings} summary note{r.summary_warnings === 1 ? '' : 's'}</ToneBadge>}
                      {r.has_approved && <ToneBadge tone="gray">Approved CV kept</ToneBadge>}
                    </div>
                  </button>
                  <div className="flex flex-wrap items-center gap-2 pb-2.5 pl-10 pr-4">
                    <LeftOutPopover row={r} />
                    <RegenChip row={r} />
                  </div>
                </div>
              ))
            )}
          </div>
          {rows.length > 0 && (
            <p className="border-t border-border px-4 py-2 text-2xs text-fg-subtle">
              J/K move · A approve, next · X tick · R regenerate · ⇧R regenerate ticked · E summary · S skip
            </p>
          )}
        </div>
        <div className="flex min-w-0 flex-1 flex-col bg-surface">
          {selected ? (
            <>
              <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-bg px-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{selected.job_title}</p>
                  <p className="truncate text-xs text-fg-subtle">{selected.company_name} · v{selected.version} · {rows.length} to review</p>
                </div>
                {version && <FitBadge version={version} />}
                <Button size="sm" variant="ghost" onClick={focusSummary}>
                  <SquarePen />
                  <span className="max-xl:hidden">Edit summary</span> <Kbd>E</Kbd>
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setRegenerating(true)} disabled={busy}>
                  <RefreshCw className={busy ? 'animate-spin' : undefined} />
                  <span className="max-xl:hidden">Regenerate</span> <Kbd>R</Kbd>
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onSkip(selected.application_id)}>
                  <SkipForward />
                  <span className="max-xl:hidden">Skip</span> <Kbd>S</Kbd>
                </Button>
                <Button size="sm" variant="ghost" asChild>
                  <Link to={`/jobs/${selected.job_id}/cv`}>CV Studio</Link>
                </Button>
                <span data-tour="review-cvs-approve" title={blocked ?? undefined}>
                  <Button size="sm" variant="default" onClick={() => onApprove(selected)} disabled={approve.isPending || !canApprove}>
                    <CircleCheck />
                    Approve <Kbd>A</Kbd>
                  </Button>
                </span>
              </div>
              {studio.isPending ? (
                <div className="grid flex-1 grid-cols-2 gap-6 p-6">
                  <Skeleton className="h-64" />
                  <Skeleton className="aspect-[1/1.294] w-full max-w-[620px]" />
                </div>
              ) : studio.error ? (
                <ErrorState error={studio.error} onRetry={() => studio.refetch()} />
              ) : studio.data && version ? (
                <Workspace key={version.id} studio={studio.data} version={version} />
              ) : null}
            </>
          ) : (
            !isPending && !error && <EmptyState icon={FileText} title="Nothing to review" description="Approved CVs move on to Applications and Outreach." />
          )}
        </div>
      </div>
      <RegenerateSelectedDialog
        key={batchKey}
        open={batchOpen}
        onClose={() => setBatchOpen(false)}
        count={picks.selected.length}
        approvedCount={pickedRows.filter((r) => r.has_approved).length}
        pending={batch.isPending}
        onSubmit={submitBatch}
      />
      <RegenerateDialog
        open={regenerating}
        onClose={() => setRegenerating(false)}
        title="Regenerate this CV"
        hint="With feedback, the summary is rewritten toward it (bullets and layout stay, the previous summary is kept in its history). Without feedback, a whole new CV is written."
        pending={busy}
        onSubmit={regenerate}
      />
    </div>
  )
}
