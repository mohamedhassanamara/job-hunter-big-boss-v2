import { Ban, ExternalLink, Search, UserPlus, UserRoundX } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { FitBadge, ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { fitBand, pluralize, relativeTime } from '@/lib/format'
import { useLookupAction, useLookups } from '@/lib/queries/library'
import type { FitBrief, LookupItem } from '@/lib/types'
import { cn } from '@/lib/utils'
import { NewContactDialog } from '@/components/app/NewContactDialog'

const brief = (score: number | null): FitBrief | null =>
  score === null
    ? null
    : { score, band: fitBand(score), status: 'ok', confidence: 'medium', hard_flag: false, flag_count: 0, stale: false, model: null, prompt_version: null }

export function LookupTab() {
  const { data, isPending, error, refetch } = useLookups()
  const act = useLookupAction()
  const [selected, setSelected] = useState<number | null>(null)
  const [entering, setEntering] = useState<LookupItem | null>(null)
  const items = data?.items ?? []
  const byId = (id: number) => items.find((i) => i.company_id === id)

  const MESSAGES = {
    skip: ['Skipped until tomorrow', ''],
    'not-found': ['Marked: nobody found', "'s jobs go to web apply"],
    never: ['Never looked up', ' is treated as a job board; its jobs go to web apply'],
    'not-aggregator': ['Kept in the queue', ' is an employer'],
  } as const
  const run = (item: LookupItem, action: keyof typeof MESSAGES) =>
    act.mutate(
      { companyId: item.company_id, action },
      {
        onSuccess: () => {
          const [title, tail] = MESSAGES[action]
          toast.success(title, {
            description: tail ? `${item.company_name}${tail}` : item.company_name,
            duration: action === 'never' || action === 'not-found' ? 8000 : undefined,
            action:
              action === 'never' || action === 'not-found'
                ? { label: 'Undo', onClick: () => act.mutate({ companyId: item.company_id, action: 'again' }) }
                : undefined,
          })
        },
        onError: (e) => toast.error(e.message),
      },
    )

  useListKeyboard({
    ids: items.map((i) => i.company_id),
    selectedId: selected,
    onSelect: setSelected,
    actions: {
      e: (id) => setEntering(byId(id) ?? null),
      n: (id) => {
        const item = byId(id)
        if (item) run(item, 'not-found')
      },
      x: (id) => {
        const item = byId(id)
        if (item) run(item, 'never')
      },
    },
    enabled: !entering,
  })

  if (isPending) return <SkeletonRows rows={6} className="mx-6 my-5" />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />

  const pct = Math.min(100, (data.used_today / Math.max(1, data.daily_cap)) * 100)
  const capped = data.used_today >= data.daily_cap
  return (
    <div className="mx-auto max-w-5xl space-y-4 px-6 py-6">
      <div data-tour="contacts-lookup-counter" className="rounded-lg border border-border bg-surface p-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold">Manual Apollo lookups</p>
            <p className="text-xs text-fg-muted">
              Companies with jobs but no imported contact: shortlisted jobs first, then the best fit, then the newest.
              Look each one up with the Apollo extension, then enter who you found (or mark nobody). The cap is in
              Settings → Contacts.
            </p>
          </div>
          <p className="shrink-0 text-sm font-medium tabular-nums">
            {data.used_today} / {data.daily_cap} <span className="text-fg-subtle">today</span>
          </p>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-hover">
          <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
        {capped && <p className="mt-2 text-xs text-warning-fg">Daily cap reached: next lookups tomorrow. You can still enter results.</p>}
      </div>
      <p className="text-xs text-fg-subtle">
        {pluralize(data.total, 'company', 'companies')} queued · <Kbd>J</Kbd> <Kbd>K</Kbd> move · <Kbd>E</Kbd> enter contact · <Kbd>N</Kbd> nobody found · <Kbd>X</Kbd> never look up
      </p>
      <div data-tour="contacts-lookups" className="rounded-lg border border-border bg-surface" role="listbox" aria-label="Lookup queue">
        {items.length === 0 ? (
          <EmptyState
            compact
            icon={Search}
            title="No lookups queued"
            description="Companies land here when they have jobs but no imported contact. Import your Apollo export first."
            action={<TourButton tour="contacts" />}
          />
        ) : (
          items.map((i) => {
            const isSel = selected === i.company_id
            return (
              <div
                key={i.company_id}
                data-row-id={i.company_id}
                role="option"
                aria-selected={isSel}
                onClick={() => setSelected(i.company_id)}
                className={cn(
                  'relative flex cursor-default items-center gap-3 border-b border-border px-4 py-3 last:border-b-0 transition-colors duration-120',
                  isSel ? 'bg-surface-selected' : 'hover:bg-surface-hover',
                )}
              >
                {isSel && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
                <FitBadge fit={brief(i.best_fit)} />
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 truncate text-sm font-medium">
                    {i.company_name}
                    {i.domain && (
                      <a
                        href={`https://${i.domain}`}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-0.5 text-xs font-normal text-fg-subtle hover:text-fg"
                      >
                        {i.domain}
                        <ExternalLink className="size-3" />
                      </a>
                    )}
                  </p>
                  <p className="flex items-center gap-1.5 truncate text-xs text-fg-muted">
                    <ToneBadge tone={i.shortlisted ? 'blue' : 'gray'} dot={false}>
                      {i.reason}
                    </ToneBadge>
                    {i.best_job_id ? (
                      <Link to={`/jobs/${i.best_job_id}`} onClick={(e) => e.stopPropagation()} className="hover:underline">
                        {i.best_job_title}
                      </Link>
                    ) : (
                      'No open job'
                    )}
                    {i.open_jobs > 1 && ` · ${pluralize(i.open_jobs, 'open job')}`} · queued {relativeTime(i.queued_at)}
                  </p>
                  {i.aggregator.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 rounded-md bg-warning-bg px-2 py-1 text-xs text-warning-fg">
                      <span>Looks like a job board: {i.aggregator.join(' · ')}.</span>
                      <button className="font-medium underline" onClick={(e) => { e.stopPropagation(); run(i, 'never') }}>
                        Never look up
                      </button>
                      <button className="underline" onClick={(e) => { e.stopPropagation(); run(i, 'not-aggregator') }}>
                        It's an employer
                      </button>
                    </div>
                  )}
                </div>
                <Button size="sm" variant="ghost" onClick={() => run(i, 'skip')}>
                  Skip
                </Button>
                <Button size="sm" variant="ghost" onClick={() => run(i, 'never')} aria-label="Never look up">
                  <Ban />
                  Never
                </Button>
                <Button size="sm" variant="ghost" onClick={() => run(i, 'not-found')}>
                  <UserRoundX />
                  Nobody found
                </Button>
                <Button
                  size="sm"
                  variant={(selected ?? items[0].company_id) === i.company_id ? 'default' : 'secondary'}
                  onClick={() => setEntering(i)}
                >
                  <UserPlus />
                  Enter contact
                </Button>
              </div>
            )
          })
        )}
      </div>
      <NewContactDialog
        key={entering?.company_id ?? 'none'}
        open={!!entering}
        title="Enter the contact you found"
        subtitle={entering ? `${entering.company_name} · every open job there gets this contact` : ''}
        submitLabel="Save contact"
        pending={act.isPending}
        onOpenChange={(o) => !o && setEntering(null)}
        onSubmit={(contact) =>
          entering &&
          act.mutate(
            { companyId: entering.company_id, action: 'found', contact },
            {
              onSuccess: () => {
                toast.success('Contact saved', { description: `${entering.company_name}: ${pluralize(entering.open_jobs, 'job')} matched` })
                setEntering(null)
              },
              onError: (e) => toast.error(e.message),
            },
          )
        }
      />
    </div>
  )
}
