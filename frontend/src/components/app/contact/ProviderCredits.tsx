import { TriangleAlert } from 'lucide-react'
import { useProviders } from '@/lib/queries/providers'
import { cn } from '@/lib/utils'

const NAMES: Record<string, string> = { hunter: 'Hunter', prospeo: 'Prospeo', apollo: 'Apollo', apify: 'Apify' }

/** "Hunter 47 · Prospeo 98 · Apollo 49 · Apify $4.98 left": what the Find contact button has left
 * this month, summed over each provider's keys. Warns when a key is disabled or empty. */
export function ProviderCredits({ className }: { className?: string }) {
  const { data } = useProviders()
  if (!data || data.keys.length === 0) return null
  const rows = Object.keys(NAMES)
    .map((p) => {
      const ks = data.keys.filter((k) => k.provider === p)
      if (ks.length === 0) return null
      const left = ks.filter((k) => !k.disabled).reduce((n, k) => n + k.remaining, 0)
      return { p, left, usd: ks[0].unit === 'usd', bad: ks.some((k) => k.disabled) }
    })
    .filter((r) => r !== null)
  return (
    <div className={cn('flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-fg-muted', className)} data-tour="provider-credits">
      {rows.map((r) => (
        <span key={r.p} className={cn('tabular-nums', (r.bad || r.left <= 0) && 'text-danger-fg')}>
          {NAMES[r.p]} {r.usd ? `$${r.left.toFixed(2)}` : Math.round(r.left * 10) / 10}
        </span>
      ))}
      <span className="text-fg-subtle">left this month</span>
      {data.warnings.length > 0 && (
        <span className="flex items-center gap-1 text-warning-fg" title={data.warnings.join('\n')}>
          <TriangleAlert className="size-3.5" />
          {data.warnings.length} key{data.warnings.length === 1 ? '' : 's'} need attention
        </span>
      )}
    </div>
  )
}
