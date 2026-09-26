import { CircleCheck, CircleSlash, CircleX, LoaderCircle } from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'
import { SOURCE_SHORT } from '@/lib/format'
import { useDiscoveryStatus } from '@/lib/queries/workflow'
import type { SourceRun } from '@/lib/types'
import { cn } from '@/lib/utils'

function Chip({ run }: { run: SourceRun }) {
  const name = SOURCE_SHORT[run.source]
  const body =
    run.status === 'running' ? (
      <>
        <LoaderCircle className="size-3.5 animate-spin text-primary" />
        {name}
      </>
    ) : run.status === 'success' ? (
      <>
        <CircleCheck className="size-3.5 text-success-dot" />
        {name} <span className="text-fg-subtle tabular-nums">{run.kept_count} kept</span>
      </>
    ) : run.status === 'failed' ? (
      <>
        <CircleX className="size-3.5 text-danger-dot" />
        {name} <span className="text-danger-fg">failed</span>
      </>
    ) : run.status === 'skipped' ? (
      <>
        <CircleSlash className="size-3.5 text-fg-subtle" />
        {name} <span className="text-fg-subtle">skipped</span>
      </>
    ) : (
      <>
        <span className="size-1.5 rounded-full bg-tone-gray-dot" />
        <span className="text-fg-subtle">{name}</span>
      </>
    )
  return (
    <Tooltip content={run.error}>
      <span className="inline-flex h-6 items-center gap-1.5 rounded-md border border-border bg-surface px-2 text-xs">
        {body}
      </span>
    </Tooltip>
  )
}

/** Slim strip shown while a discovery run is in progress. */
export function DiscoveryProgress({ className }: { className?: string }) {
  const { data } = useDiscoveryStatus()
  if (!data?.running || !data.run) return null
  const done = data.run.sources.filter((s) => !['pending', 'running'].includes(s.status)).length
  const total = data.run.sources.length || 1
  return (
    <div className={cn('relative border-b border-border bg-primary-subtle/50 px-6 py-2', className)}>
      <div className="absolute inset-x-0 top-0 h-0.5 bg-border">
        <div
          className="h-full bg-primary transition-[width] duration-200"
          style={{ width: `${Math.max(8, (done / total) * 100)}%` }}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs font-medium">
          Discovering… {done}/{total} sources
        </span>
        {data.run.sources.map((s) => (
          <Chip key={s.id} run={s} />
        ))}
      </div>
    </div>
  )
}
