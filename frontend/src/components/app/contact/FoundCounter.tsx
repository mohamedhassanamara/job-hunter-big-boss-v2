import { TriangleAlert } from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/** "Contacts found today 4 / 10": your Apollo extension's daily limit (Settings → Contacts).
 * A warning from 80%; it never blocks. */
export function FoundCounter({ found, limit, className }: { found: number; limit: number; className?: string }) {
  const pct = limit > 0 ? Math.min(1, found / limit) : 0
  const level = found >= limit ? 'danger' : pct >= 0.8 ? 'warning' : 'ok'
  return (
    <Tooltip content="Contacts you entered today (found with the Apollo extension). The limit is your extension's daily quota, set in Settings → Contacts.">
      <div className={cn('flex items-center gap-2 text-xs', className)} data-tour="found-counter">
        {level !== 'ok' && <TriangleAlert className={cn('size-3.5', level === 'danger' ? 'text-danger-fg' : 'text-warning-fg')} />}
        <span className={cn('tabular-nums', level === 'danger' ? 'text-danger-fg' : level === 'warning' ? 'text-warning-fg' : 'text-fg-muted')}>
          {found} / {limit} found today
          {level === 'danger' ? ' · extension limit reached' : level === 'warning' ? ' · close to the extension limit' : ''}
        </span>
        <span className="h-1.5 w-16 overflow-hidden rounded-full bg-bg-subtle">
          <span
            className={cn('block h-full rounded-full', level === 'danger' ? 'bg-danger-solid' : level === 'warning' ? 'bg-warning-dot' : 'bg-primary')}
            style={{ width: `${pct * 100}%` }}
          />
        </span>
      </div>
    </Tooltip>
  )
}
