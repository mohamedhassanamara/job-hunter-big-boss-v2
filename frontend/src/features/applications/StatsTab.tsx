import { BarChart3, SearchX } from 'lucide-react'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { countryName, pluralize, SOURCE_LABELS } from '@/lib/format'
import { useStats } from '@/lib/queries/tracking'
import { pct } from '@/lib/tracking'
import type { Rate, Source, StatsGroup } from '@/lib/types'
import { useTrackingFilters } from './filters'
import { TrackingFilterBar } from './TrackingFilterBar'

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <p className="text-xs font-medium text-fg-subtle">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight tabular-nums">{value}</p>
      <p className="text-xs text-fg-muted">{detail}</p>
    </div>
  )
}

function RateCell({ rate }: { rate: Rate }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-subtle">
        <div className="h-full rounded-full bg-primary" style={{ width: `${Math.round((rate.rate ?? 0) * 100)}%` }} />
      </div>
      <span className="w-20 text-right text-xs tabular-nums">
        {pct(rate.rate)} <span className="text-fg-subtle">({rate.count}/{rate.total})</span>
      </span>
    </div>
  )
}

function GroupTable({ title, groups, label }: { title: string; groups: StatsGroup[]; label: (g: string) => string }) {
  return (
    <section className="rounded-lg border border-border bg-surface shadow-sm">
      <div className="grid h-11 grid-cols-[minmax(0,1fr)_64px_1fr_1fr] items-center gap-4 border-b border-border px-4 text-xs font-medium text-fg-subtle">
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        <span className="text-right">Applied</span>
        <span>Response rate</span>
        <span>Interview rate</span>
      </div>
      {groups.map((g) => (
        <div key={g.group} className="grid grid-cols-[minmax(0,1fr)_64px_1fr_1fr] items-center gap-4 border-b border-border px-4 py-2.5 last:border-b-0">
          <span className="truncate text-sm">{label(g.group)}</span>
          <span className="text-right text-sm tabular-nums">{g.applied}</span>
          <RateCell rate={g.response} />
          <RateCell rate={g.interview} />
        </div>
      ))}
    </section>
  )
}

/** A small stats table: a label column, then numbers and rate bars. */
function Table({ title, head, rows }: { title: string; head: string[]; rows: { key: string; label: string; cells: (number | Rate)[] }[] }) {
  const cols = `minmax(0,1fr) ${head.map((h) => (h.endsWith('rate') ? '1fr' : '72px')).join(' ')}`
  return (
    <section className="rounded-lg border border-border bg-surface shadow-sm">
      <div className="grid h-11 items-center gap-4 border-b border-border px-4 text-xs font-medium text-fg-subtle" style={{ gridTemplateColumns: cols }}>
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        {head.map((h) => (
          <span key={h} className={h.endsWith('rate') ? undefined : 'text-right'}>
            {h}
          </span>
        ))}
      </div>
      {rows.map((r) => (
        <div key={r.key} className="grid items-center gap-4 border-b border-border px-4 py-2.5 last:border-b-0" style={{ gridTemplateColumns: cols }}>
          <span className="truncate text-sm">{r.label}</span>
          {r.cells.map((c, i) => (typeof c === 'number' ? <span key={i} className="text-right text-sm tabular-nums">{c}</span> : <RateCell key={i} rate={c} />))}
        </div>
      ))}
    </section>
  )
}

export function StatsTab() {
  const url = useSearchParamState()
  const { filters, active, clear } = useTrackingFilters()
  const { data, isPending, error, refetch } = useStats(filters)

  let body: React.ReactNode
  if (isPending) {
    body = (
      <div className="space-y-4">
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-48" />
      </div>
    )
  } else if (error) {
    body = <ErrorState error={error} onRetry={() => refetch()} />
  } else if (data.applied === 0) {
    body = active ? (
      <EmptyState icon={SearchX} title="No applications in this selection" action={<Button size="sm" onClick={clear}>Clear filters</Button>} />
    ) : (
      <EmptyState
        icon={BarChart3}
        title="No numbers yet"
        description="Stats start with your first application: weekly volume, response and interview rates, and how long answers take."
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
  } else {
    const max = Math.max(...data.per_week.map((w) => w.count), 1)
    body = (
      <div className="space-y-4">
        <div className="grid grid-cols-4 gap-4 max-lg:grid-cols-2">
          <Metric label="Applied" value={String(data.applied)} detail={pluralize(data.per_week.length, 'week')} />
          <Metric label="Response rate" value={pct(data.response.rate)} detail={`${data.response.count} of ${data.response.total} got an answer`} />
          <Metric label="Interview rate" value={pct(data.interview.rate)} detail={`${data.interview.count} of ${data.interview.total} reached an interview`} />
          <Metric
            label="Median days to first answer"
            value={data.median_days_to_first_response === null ? '—' : String(data.median_days_to_first_response)}
            detail="Reply or interview, whichever came first"
          />
        </div>
        <section data-tour="applications-weekly" className="rounded-lg border border-border bg-surface p-4 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold">Applications per week</h2>
          <div className="flex h-40 items-end gap-2">
            {data.per_week.map((w) => (
              <Tooltip key={w.week} content={`${w.week}: ${pluralize(w.count, 'application')}`}>
                <div className="flex h-full min-w-8 flex-1 flex-col items-center justify-end gap-1">
                  <span className="text-xs text-fg-muted tabular-nums">{w.count}</span>
                  <div className="w-full max-w-12 rounded-t-sm bg-primary" style={{ height: `${(w.count / max) * 100}%` }} />
                  <span className="text-2xs whitespace-nowrap text-fg-subtle">{w.week.replace(/^\d{4}-/, '')}</span>
                </div>
              </Tooltip>
            ))}
          </div>
        </section>
        <GroupTable
          title={`By route · ${data.both_routes} job${data.both_routes === 1 ? '' : 's'} with both`}
          groups={data.by_route}
          label={(g) => ({ web: 'Website only', email: 'Email only', both: 'Website + email' })[g] ?? g}
        />
        <Table
          title="Replies by track"
          head={['Reached', 'Reply rate']}
          rows={data.by_channel.map((c) => ({
            key: c.group,
            label: { application: 'Application (website)', email: 'Email', linkedin: 'LinkedIn (requests sent)' }[c.group],
            cells: [c.reached, { count: c.count, total: c.total, rate: c.rate }],
          }))}
        />
        <Table
          title="LinkedIn by group"
          head={['Requests', 'Accepted rate', 'Reply rate']}
          rows={data.linkedin_groups.map((g) => ({
            key: g.group,
            label: { hiring_team: 'Hiring team', alumni: 'Alumni', others: 'Team leads, recruiters, others' }[g.group],
            cells: [g.sent, g.accepted, g.replied],
          }))}
        />
        <Table
          title="Jobs by source"
          head={['Jobs', 'Past New', 'Applied', 'Replied']}
          rows={data.by_origin.map((o) => ({ key: o.group, label: o.group === 'linkedin_import' ? 'LinkedIn (your imports)' : 'Discovery', cells: [o.jobs, o.past_new, o.applied, o.replied] }))}
        />
        <GroupTable title="By track" groups={data.by_track} label={(g) => (g === '(none)' ? 'No track' : g)} />
        <GroupTable title="By country" groups={data.by_country} label={(g) => (g === '(none)' ? 'Remote / none' : countryName(g))} />
        <GroupTable title="By source" groups={data.by_source} label={(g) => SOURCE_LABELS[g as Source] ?? g} />
        <p className="text-xs text-fg-subtle">Counts sit next to every rate: with a handful of applications, one reply moves a percentage a lot.</p>
      </div>
    )
  }

  return (
    <>
      <TrackingFilterBar />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5" data-tour="applications-stats">
        {body}
      </div>
    </>
  )
}
