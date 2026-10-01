import { ArrowRight, RefreshCw, TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { useCVFit, useRerunCVFit } from '@/lib/queries/critique'
import { cn } from '@/lib/utils'

/** Fit before/after for an approved CV: the job's fit (your master experience) → the fit
 * against this CV (gemma, one call, stored apart), plus the evidence check (no model). */
export function CVFitStrip({ cvId }: { cvId: number }) {
  const { data } = useCVFit(cvId)
  const rerun = useRerunCVFit()
  if (!data) return null
  const lx = data.lexical
  const delta = data.score != null && data.base_score != null ? data.score - data.base_score : null
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-border bg-bg-subtle px-6 py-2 text-sm" data-tour="cv-fit">
      <span className="flex items-center gap-1.5">
        <span className="text-fg-muted">Fit</span>
        <span className="tabular-nums">{data.base_score ?? '—'}</span>
        <ArrowRight className="size-3.5 text-fg-subtle" />
        {data.status === 'pending' ? (
          <span className="text-fg-subtle">scoring this CV…</span>
        ) : data.status === 'failed' ? (
          <span className="flex items-center gap-1 text-warning-fg">
            <TriangleAlert className="size-3.5" />
            not scored
            <Button size="xs" variant="ghost" onClick={() => rerun.mutate(cvId, { onError: (e) => toast.error(e.message) })} disabled={rerun.isPending}>
              <RefreshCw />
              Try again
            </Button>
          </span>
        ) : (
          <Tooltip content={`Scored against this CV by ${data.model} (${data.prompt_version}); the job's own fit is unchanged`}>
            <span className={cn('font-medium tabular-nums', delta != null && delta > 0 && 'text-success-fg', delta != null && delta < 0 && 'text-danger-fg')}>
              {data.score}
              {delta != null && ` (${delta > 0 ? '+' : ''}${delta})`}
            </span>
          </Tooltip>
        )}
      </span>
      {lx.checkable > 0 && (
        <Tooltip content="Of the listing's checkable lines your experience backs, how many are visible on the first screen (summary, skills, role titles, first ten bullets): your master experience → this CV">
          <span className="text-fg-muted">
            Shown first: <span className="tabular-nums text-fg">{lx.shown_before}</span> → <span className="tabular-nums text-fg">{lx.shown_after ?? '—'}</span> of {lx.evidenced} backed ({lx.checkable} checkable)
          </span>
        </Tooltip>
      )}
      {lx.dropped.length > 0 && (
        <span className="text-warning-fg">
          Left out: {lx.dropped.slice(0, 4).join(', ')}
          {lx.dropped.length > 4 ? '…' : ''}
        </span>
      )}
      {lx.unbacked.length > 0 && <span className="text-danger-fg">Not in your experience: {lx.unbacked.slice(0, 4).join(', ')}</span>}
      {lx.years && <span className="text-fg-muted">{lx.years}</span>}
    </div>
  )
}
