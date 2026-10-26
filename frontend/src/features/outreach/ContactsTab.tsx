import { ExternalLink, UserRoundCheck, UserRoundSearch } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { Link } from 'react-router'
import { FitBadge, ToneBadge } from '@/components/app/badges'
import { FindBatchButton } from '@/components/app/contact/FindBatch'
import { FoundCounter } from '@/components/app/contact/FoundCounter'
import { GetContactPanel } from '@/components/app/contact/GetContactPanel'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useToGet } from '@/lib/queries/getContact'
import { cn } from '@/lib/utils'

/** Contacts to get: one job at a time, the Get contact panel beside the list. Keys: J/K move,
 * V still there, L left, E edit, P paste box, ⌘↵ save, N nobody found, X never look up. */
export function ContactsTab() {
  const url = useSearchParamState()
  const selectedId = url.get('app') ? Number(url.get('app')) : null
  const { data, isPending, error, refetch } = useToGet()
  const items = useMemo(() => data?.items ?? [], [data])
  const ids = useMemo(() => items.map((i) => i.application_id), [items])
  const selected = items.find((i) => i.application_id === selectedId) ?? items[0]

  useEffect(() => {
    if (!selectedId && items[0]) url.set({ app: items[0].application_id })
  }, [selectedId, items, url])

  const select = (id: number) => url.set({ app: id })
  // After saving or verifying, the job leaves the queue: move on to the next one.
  const next = () => {
    const current = new URLSearchParams(window.location.search).get('app')
    const index = ids.indexOf(Number(current))
    url.set({ app: ids[index + 1] ?? ids[index - 1] ?? null })
  }
  useListKeyboard({ ids, selectedId: selected?.application_id ?? null, onSelect: select })

  return (
    <div className="flex h-full min-h-0">
      <div data-tour="contacts-to-get" className="flex w-[360px] shrink-0 flex-col border-r border-border bg-bg max-xl:w-[300px]">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
          {data ? <FoundCounter found={data.found_today} limit={data.daily_limit} /> : <span className="h-5" />}
          <FindBatchButton className="ml-auto" />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isPending ? (
            <SkeletonRows rows={5} />
          ) : error ? (
            <ErrorState compact error={error} onRetry={() => refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              compact
              icon={UserRoundCheck}
              title="Every contact is found and verified"
              description="Jobs join this list once you move them past New (shortlist them) and they need a contact or a check."
              action={<TourButton tour="get-contact" />}
            />
          ) : (
            items.map((i) => (
              <button
                key={i.application_id}
                data-row-id={i.application_id}
                onClick={() => select(i.application_id)}
                className={cn(
                  'relative block w-full border-b border-border px-4 py-3 text-left transition-colors duration-120',
                  selected?.application_id === i.application_id ? 'bg-surface-selected' : 'hover:bg-surface-hover',
                )}
              >
                {selected?.application_id === i.application_id && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
                <div className="flex items-center gap-2">
                  <span className="flex-1 truncate text-sm font-medium">{i.company_name}</span>
                  <FitBadge fit={i.fit} size="sm" />
                </div>
                <p className="truncate text-xs text-fg-muted">{i.job_title}</p>
                <p className="mt-1.5 flex items-center gap-2 text-xs">
                  <ToneBadge tone={i.state === 'verify' ? 'amber' : i.nobody_found ? 'gray' : 'blue'}>
                    {i.state === 'verify' ? (i.stale ? 'Verify again' : 'Verify') : i.nobody_found ? 'Nobody found' : 'Get contact'}
                  </ToneBadge>
                  {i.contact_name && <span className="truncate text-fg-subtle">{i.contact_name}</span>}
                </p>
              </button>
            ))
          )}
        </div>
        {items.length > 0 && <p className="border-t border-border px-4 py-2 text-2xs text-fg-subtle">J/K move · V verified · L left · P paste · ⌘↵ save</p>}
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto bg-surface">
        {selected ? (
          <div className="mx-auto max-w-3xl space-y-4 px-6 py-5">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-base font-semibold">{selected.company_name}</p>
                <p className="text-sm text-fg-muted">
                  {selected.job_title} · {selected.stage_label}
                </p>
              </div>
              <Button size="sm" variant="ghost" asChild>
                <Link to={`/jobs/${selected.job_id}`}>
                  Open the job
                  <ExternalLink />
                </Link>
              </Button>
            </div>
            <GetContactPanel key={selected.application_id} appId={selected.application_id} hotkeys onDone={next} />
          </div>
        ) : (
          !isPending &&
          !error && (
            <EmptyState
              icon={UserRoundSearch}
              title="No contacts to get"
              description="When you shortlist a job, it comes here if its company has no contact yet, or its contact needs a check. Then the email can be drafted."
              action={
                <div className="flex gap-2">
                  <Button size="sm" asChild>
                    <Link to="/pipeline">Open pipeline</Link>
                  </Button>
                  <TourButton tour="get-contact" />
                </div>
              }
            />
          )
        )}
      </div>
    </div>
  )
}
