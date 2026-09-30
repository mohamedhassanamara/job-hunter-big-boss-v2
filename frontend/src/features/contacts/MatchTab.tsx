import { GitMerge } from 'lucide-react'
import { toast } from 'sonner'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { absoluteDate, countryName, pluralize } from '@/lib/format'
import { useMatchReport, useRunMatch } from '@/lib/queries/library'
import type { MatchGroup } from '@/lib/types'

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <p className="text-xs font-medium text-fg-subtle">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight tabular-nums">{value}</p>
      {detail && <p className="text-xs text-fg-muted">{detail}</p>}
    </div>
  )
}

function Split({ g }: { g: MatchGroup }) {
  const w = (n: number) => `${(n / Math.max(1, g.jobs)) * 100}%`
  return (
    <div className="flex h-1.5 overflow-hidden rounded-full bg-surface-hover">
      <div className="h-full bg-success-dot" style={{ width: w(g.with_contact) }} />
      <div className="h-full bg-warning-dot" style={{ width: w(g.to_get) }} />
      <div className="h-full bg-fg-subtle" style={{ width: w(g.no_contact) }} />
    </div>
  )
}

function GroupTable({ title, groups, label }: { title: string; groups: MatchGroup[]; label: (g: string) => string }) {
  return (
    <section className="rounded-lg border border-border bg-surface shadow-sm">
      <div className="grid h-11 grid-cols-[minmax(0,1fr)_64px_88px_88px_88px_1fr] items-center gap-3 border-b border-border px-4 text-xs font-medium text-fg-subtle">
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        <span className="text-right">Jobs</span>
        <span className="text-right">Contact</span>
        <span className="text-right">To get</span>
        <span className="text-right">None</span>
        <span />
      </div>
      {groups.map((g) => (
        <div key={g.group} className="grid grid-cols-[minmax(0,1fr)_64px_88px_88px_88px_1fr] items-center gap-3 border-b border-border px-4 py-2.5 text-sm tabular-nums last:border-b-0">
          <span className="truncate">{label(g.group)}</span>
          <span className="text-right">{g.jobs}</span>
          <span className="text-right">{g.with_contact}</span>
          <span className="text-right">{g.to_get}</span>
          <span className="text-right">{g.no_contact}</span>
          <Split g={g} />
        </div>
      ))}
    </section>
  )
}

export function MatchTab() {
  const { data, isPending, error, refetch } = useMatchReport()
  const run = useRunMatch()
  const trigger = () =>
    run.mutate(undefined, {
      onSuccess: (r) => toast.success('Matching finished', { description: `${pluralize(r.changed ?? 0, 'job')} changed` }),
      onError: (e) => toast.error(e.message),
    })

  if (isPending) return <Skeleton className="mx-6 my-5 h-64" />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />

  return (
    <div className="mx-auto max-w-5xl space-y-4 px-6 py-6" data-tour="contacts-match">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-fg-muted">
          Every open job is matched to the most relevant contact at its company; jobs without one (past New) join Outreach → Contacts to get.
          Matching also runs after each discovery run and each import.
          {data && ` Last run ${absoluteDate(data.at)}.`}
        </p>
        <Button variant="default" size="sm" onClick={trigger} disabled={run.isPending}>
          <GitMerge />
          {run.isPending ? 'Matching…' : 'Run matching now'}
        </Button>
      </div>
      {!data ? (
        <EmptyState
          icon={GitMerge}
          title="No matching report yet"
          description="Import your Apollo contacts, then run matching to see how many jobs have someone to write to."
          action={<TourButton tour="contacts" />}
        />
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4 max-lg:grid-cols-2">
            <Metric label="Open jobs" value={String(data.totals.jobs)} />
            <Metric label="With a contact" value={String(data.totals.with_contact)} detail={`${Math.round((data.totals.with_contact / Math.max(1, data.totals.jobs)) * 100)}% of open jobs`} />
            <Metric label="Contacts to get" value={String(data.contacts_to_get)} detail={`${pluralize(data.totals.to_get, 'open job')} with nobody yet`} />
            <Metric label="No contact" value={String(data.totals.no_contact)} detail="Nobody found, or never looked up → web apply" />
          </div>
          <p className="text-xs text-fg-subtle">
            {pluralize(data.contacts, 'contact')} at {pluralize(data.companies_with_contacts, 'company', 'companies')}.
            Bars: <span className="text-success-fg">contact</span> · <span className="text-warning-fg">to get</span> · none.
          </p>
          <GroupTable title="By track" groups={data.by_track} label={(g) => (g === '(none)' ? 'No track' : g)} />
          <GroupTable title="By country" groups={data.by_country} label={(g) => (g === '(remote)' ? 'Remote / none' : countryName(g))} />
        </>
      )}
    </div>
  )
}
