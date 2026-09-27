import { CloudOff } from 'lucide-react'
import { useScoringStatus } from '@/lib/queries/workflow'
import { cn } from '@/lib/utils'

/** Shown in Discover and on Today when a cloud usage limit switched scoring to the local model.
 * The next run tries the cloud model again. */
export function ScoringFallbackNotice({ className }: { className?: string }) {
  const { data } = useScoringStatus()
  const run = data?.run
  if (!run?.fallback_reason) return null
  return (
    <div
      role="status"
      className={cn('flex items-start gap-2.5 border-b border-tone-amber-border bg-warning-bg px-6 py-2 text-xs text-warning-fg', className)}
    >
      <CloudOff className="mt-0.5 size-3.5 shrink-0" />
      <span className="flex-1">
        {run.finished ? 'The last scoring run' : 'Scoring'} switched from <span className="font-mono">{run.primary_model}</span> to local{' '}
        <span className="font-mono">{run.fallback_model}</span> (slower): {run.fallback_reason}.{' '}
        The next run tries the cloud model again.
      </span>
    </div>
  )
}
