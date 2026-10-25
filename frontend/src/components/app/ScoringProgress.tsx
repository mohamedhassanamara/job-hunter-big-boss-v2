import { CircleAlert, Copy, LoaderCircle, Pause, RefreshCw, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'
import { ScoringFallbackNotice } from '@/components/app/ScoringFallbackNotice'
import { Button } from '@/components/ui/button'
import { pluralize } from '@/lib/format'
import { clockTime, relativeTime } from '@/lib/format'
import { useCancelScoring, useContinueWith, useRescore, useScoringStatus, useStartScoring } from '@/lib/queries/workflow'
import { cn } from '@/lib/utils'

function eta(seconds: number | null) {
  if (!seconds) return null
  if (seconds < 90) return `~${seconds}s left`
  return `~${Math.round(seconds / 60)} min left`
}

/**
 * Scoring state for Discover: progress while the background queue runs, a blocked reason
 * (Ollama down / model missing), and prompts for unscored / failed jobs.
 */
export function ScoringProgress({ className }: { className?: string }) {
  const { data } = useScoringStatus()
  const rescore = useRescore()
  const cancel = useCancelScoring()
  const start = useStartScoring()
  const continueWith = useContinueWith()
  if (!data) return null
  const run = data.run
  const ollama = run?.fallback_model || 'gemma4:31b-cloud'

  const queue = (scope: 'failed' | 'unscored') =>
    rescore.mutate(
      { scope },
      {
        onSuccess: (r) => toast.success(`${pluralize(r.enqueued, 'job')} queued for scoring`),
        onError: (e) => toast.error(e.message),
      },
    )

  if (data.waiting_until) {
    return (
      <div className={cn('flex flex-wrap items-center gap-3 border-b border-tone-amber-border bg-warning-bg px-6 py-2 text-sm text-warning-fg', className)} data-tour="scoring-waiting">
        <Pause className="size-4 shrink-0" />
        <span className="flex-1">
          {data.blocked ?? 'The Gemini quota is used up.'} {pluralize(data.queued, 'job')} wait{data.queued === 1 ? 's' : ''}: scoring resumes by itself at {clockTime(data.waiting_until)} ({relativeTime(data.waiting_until)}).
        </span>
        <Button
          size="xs"
          variant="ghost"
          onClick={() => continueWith.mutate(ollama, { onSuccess: () => toast.success(`Scoring the rest with ${ollama}`), onError: (e) => toast.error(e.message) })}
          disabled={continueWith.isPending}
        >
          Score the rest now with {ollama}
        </Button>
      </div>
    )
  }

  if (data.override_model && data.running) {
    return (
      <div className={cn('flex items-center gap-3 border-b border-border bg-primary-subtle/50 px-6 py-2 text-xs', className)}>
        <LoaderCircle className="size-3.5 animate-spin text-primary" />
        <span className="font-medium">
          Scoring {data.done + data.failed} / {data.total} with {data.override_model} (your choice, until the app restarts)
        </span>
        <Button size="xs" variant="ghost" className="ml-auto" onClick={() => continueWith.mutate(null)}>
          Back to {data.model}
        </Button>
      </div>
    )
  }

  if (data.blocked) {
    const command = data.blocked.match(/ollama pull \S+/)?.[0]
    return (
      <div className={cn('flex items-center gap-3 border-b border-tone-red-border bg-danger-bg px-6 py-2 text-sm', className)}>
        <CircleAlert className="size-4 shrink-0 text-danger-fg" />
        <span className="flex-1 text-danger-fg">Scoring paused: {data.blocked}</span>
        {command && (
          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              void navigator.clipboard.writeText(command)
              toast.success('Command copied')
            }}
          >
            <Copy />
            Copy command
          </Button>
        )}
        <Button size="xs" onClick={() => start.mutate(undefined, { onError: (e) => toast.error(e.message) })}>
          <RefreshCw />
          Retry
        </Button>
      </div>
    )
  }

  if (data.running) {
    const details = [
      run?.model,
      run?.concurrency_limit ? `${run.concurrency_limit} parallel` : null,
      run?.retried_429 ? `${pluralize(run.retried_429, 'busy retry', 'busy retries')}` : null,
    ].filter(Boolean)
    const pct = data.total ? Math.round(((data.done + data.failed) / data.total) * 100) : 0
    return (
      <>
        <ScoringFallbackNotice />
        <div className={cn('relative border-b border-border bg-primary-subtle/50 px-6 py-2', className)}>
          <div className="absolute inset-x-0 top-0 h-0.5 bg-border">
            <div className="h-full bg-primary transition-[width] duration-200" style={{ width: `${Math.max(4, pct)}%` }} />
          </div>
          <div className="flex items-center gap-3 text-xs">
            <LoaderCircle className="size-3.5 animate-spin text-primary" />
            <span className="font-medium">
              Scoring {data.done + data.failed} / {data.total}
            </span>
            {data.in_progress[0] && <span className="truncate text-fg-muted">· {data.in_progress[0].title}</span>}
            {data.failed > 0 && <span className="text-danger-fg">· {data.failed} failed</span>}
            {details.length > 0 && <span className="text-fg-subtle">· {details.join(' · ')}</span>}
            <span className="ml-auto text-fg-subtle tabular-nums">
              {[eta(data.eta_seconds), data.avg_seconds ? `${data.avg_seconds}s/job` : null].filter(Boolean).join(' · ')}
            </span>
            <Button size="xs" variant="ghost" onClick={() => cancel.mutate()}>
              <X />
              Cancel
            </Button>
          </div>
        </div>
      </>
    )
  }

  const notices: { key: string; text: string; action: string; scope: 'failed' | 'unscored' }[] = []
  if (data.unscored) notices.push({ key: 'u', text: `${pluralize(data.unscored, 'job')} not scored yet`, action: 'Score them', scope: 'unscored' })
  if (data.failed_jobs) notices.push({ key: 'f', text: `${pluralize(data.failed_jobs, 'job')} failed to score`, action: 'Retry failed', scope: 'failed' })
  if (!notices.length) return <ScoringFallbackNotice />
  return (
    <>
      <ScoringFallbackNotice />
      <div className={cn('flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border bg-bg-subtle px-6 py-2 text-xs', className)}>
        <Sparkles className="size-3.5 text-fg-subtle" />
        {notices.map((n) => (
          <span key={n.key} className="inline-flex items-center gap-2 text-fg-muted">
            {n.text}
            <Button
              size="xs"
              variant="ghost"
              className="text-primary"
              onClick={() => queue(n.scope)}
              disabled={rescore.isPending}
            >
              {n.action}
            </Button>
          </span>
        ))}
      </div>
    </>
  )
}
