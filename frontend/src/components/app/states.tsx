import { CircleAlert, type LucideIcon, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  compact,
}: {
  icon: LucideIcon
  title: string
  description?: React.ReactNode
  action?: React.ReactNode
  className?: string
  compact?: boolean
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'gap-2 px-4 py-8' : 'gap-3 px-6 py-16',
        className,
      )}
    >
      <div
        className={cn(
          'flex items-center justify-center rounded-lg border border-border bg-surface text-fg-subtle shadow-sm',
          compact ? 'size-8' : 'size-10',
        )}
      >
        <Icon className={compact ? 'size-4' : 'size-5'} strokeWidth={1.75} />
      </div>
      <div className="max-w-sm space-y-1">
        <p className={cn('font-medium text-fg', compact ? 'text-sm' : 'text-base')}>{title}</p>
        {description && <p className="text-sm text-fg-muted">{description}</p>}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}

export function ErrorState({
  error,
  onRetry,
  className,
  compact,
}: {
  error: unknown
  onRetry?: () => void
  className?: string
  compact?: boolean
}) {
  const message =
    error instanceof ApiError || error instanceof Error ? error.message : 'Something went wrong'
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center gap-3 text-center',
        compact ? 'px-4 py-6' : 'px-6 py-16',
        className,
      )}
    >
      <div className="flex size-9 items-center justify-center rounded-lg bg-danger-bg text-danger-fg">
        <CircleAlert className="size-4.5" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium">Couldn't load this</p>
        <p className="max-w-sm text-sm text-fg-muted">{message}</p>
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          <RefreshCw />
          Retry
        </Button>
      )}
    </div>
  )
}

const WIDTHS = ['w-2/3', 'w-1/2', 'w-3/5', 'w-3/4']

export function SkeletonRows({ rows = 8, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('divide-y divide-border', className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          <Skeleton className="h-6 w-9" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className={cn('h-3.5', WIDTHS[i % WIDTHS.length])} />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <Skeleton className="h-5 w-16" />
        </div>
      ))}
    </div>
  )
}
