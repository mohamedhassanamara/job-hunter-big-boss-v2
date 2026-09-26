import { ArrowRight, Search } from 'lucide-react'
import { Link } from 'react-router'
import { FitBadge } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { fitBand, relativeTime } from '@/lib/format'
import { useLookups } from '@/lib/queries/library'

export function LookupTab() {
  const { data, isPending, error, refetch } = useLookups()
  if (isPending) return <SkeletonRows rows={4} className="mx-6 my-5" />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />

  const pct = Math.min(100, (data.used_today / Math.max(1, data.daily_cap)) * 100)
  return (
    <div className="mx-auto max-w-4xl space-y-4 px-6 py-6">
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold">Manual Apollo lookups</p>
            <p className="text-xs text-fg-muted">
              Tier 2 of contact resolution. You run these with the Apollo extension, which has a small daily cap.
            </p>
          </div>
          <p className="text-sm font-medium tabular-nums">
            {data.used_today} / {data.daily_cap} <span className="text-fg-subtle">used today</span>
          </p>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-hover">
          <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="rounded-lg border border-border bg-surface">
        {data.items.length === 0 ? (
          <EmptyState
            compact
            icon={Search}
            title="No lookups queued"
            description="Queue a lookup from a job without a contact."
          />
        ) : (
          data.items.map((i) => (
            <Link
              key={i.application_id}
              to={`/jobs/${i.job_id}`}
              className="flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0 hover:bg-surface-hover"
            >
              <FitBadge fit={i.fit !== null ? { score: i.fit, band: fitBand(i.fit) } : null} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{i.company_name}</p>
                <p className="truncate text-xs text-fg-muted">{i.job_title}</p>
              </div>
              <span className="text-xs text-fg-subtle">Queued {relativeTime(i.queued_at)}</span>
              <ArrowRight className="size-4 text-fg-subtle" />
            </Link>
          ))
        )}
      </div>
    </div>
  )
}
