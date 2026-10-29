import { ArrowRight, Check, ListChecks, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { FitBadge, StageBadge, ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { useTriageActions } from '@/hooks/useTriageActions'
import { relativeTime } from '@/lib/format'
import { useJobs } from '@/lib/queries/jobs'
import { useCapturedJobs, useMarkJobReviewed } from '@/lib/queries/linkedin'
import { cn } from '@/lib/utils'

/** Jobs saved with the extension (or the bookmark). They wait here while still New; anything the
 * capture looked unsure about is flagged and listed first, and "Looks right" clears it. */
export function CapturedJobs({ highlight }: { highlight: number | null }) {
  const jobs = useJobs({ source: ['linkedin'], stage: 'all', sort: 'newest' }, { limit: 200 })
  const review = useCapturedJobs()
  const reviewed = useMarkJobReviewed()
  const triage = useTriageActions()
  const state = new Map((review.data?.items ?? []).map((r) => [r.job_id, r]))
  const items = [...(jobs.data?.items ?? [])].sort((a, b) => {
    const rank = (id: number, closed: boolean) => (state.get(id)?.needs_review ? 0 : closed ? 2 : 1)
    return rank(a.id, a.application.stage === 'closed') - rank(b.id, b.application.stage === 'closed')
  })
  return (
    <div data-tour="linkedin-jobs">
      {jobs.isPending || review.isPending ? (
        <SkeletonRows rows={4} />
      ) : jobs.error || review.error ? (
        <ErrorState compact error={jobs.error ?? review.error} onRetry={() => void jobs.refetch().then(() => review.refetch())} />
      ) : items.length === 0 ? (
        <EmptyState
          compact
          icon={ArrowRight}
          title="No LinkedIn jobs yet"
          description="Open a job on LinkedIn and press “Save job” in the browser extension: it's saved here at once, scored, and flagged if anything looks misread."
          action={<TourButton tour="linkedin" />}
        />
      ) : (
        <ul>
          {items.map((j) => {
            const r = state.get(j.id)
            const closed = j.application.stage === 'closed'
            return (
              <li key={j.id} className={cn('border-b border-border last:border-b-0', highlight === j.id && 'bg-primary-subtle', closed && 'opacity-60')}>
                <div className="flex items-start gap-3 px-4 py-2.5">
                  <Link to={`/jobs/${j.id}`} className="min-w-0 flex-1 hover:underline">
                    <p className="truncate text-sm font-medium">{j.title}</p>
                    <p className="truncate text-xs text-fg-muted">
                      {j.company.name} · {j.location || 'location unknown'} · saved {relativeTime(j.discovered_at)}
                    </p>
                  </Link>
                  {r?.needs_review && (
                    <ToneBadge tone="amber" dot={false}>
                      Needs review
                    </ToneBadge>
                  )}
                  <StageBadge stage={j.application.stage} label={j.application.stage_label} />
                  <FitBadge fit={j.fit} size="sm" />
                </div>
                {r?.needs_review && (
                  <div className="flex items-start gap-3 bg-warning-bg px-4 py-2 text-xs text-warning-fg">
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                    <ul className="min-w-0 flex-1 space-y-0.5">
                      {r.flags.map((f) => (
                        <li key={f.code}>{f.text}</li>
                      ))}
                    </ul>
                    <Button
                      size="xs"
                      variant="secondary"
                      onClick={() => reviewed.mutate(j.id, { onError: (e) => toast.error(e.message) })}
                    >
                      <Check />
                      Looks right
                    </Button>
                  </div>
                )}
                {j.application.stage === 'new' && (
                  <div className="flex gap-2 px-4 pb-2">
                    <Button size="xs" variant="ghost" onClick={() => triage.shortlist({ jobId: j.id, title: j.title, company: j.company.name })}>
                      <ListChecks />
                      Shortlist
                    </Button>
                    <Button size="xs" variant="ghost" onClick={() => triage.dismiss({ jobId: j.id, title: j.title, company: j.company.name })}>
                      Dismiss
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
