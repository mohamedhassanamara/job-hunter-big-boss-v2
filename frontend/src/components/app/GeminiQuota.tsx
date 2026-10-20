import { KeyRound } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { clockTime, pluralize, relativeTime } from '@/lib/format'
import { useEnableGeminiKey, useScoringQuota } from '@/lib/queries/workflow'
import { cn } from '@/lib/utils'
import { ToneBadge } from './badges'

/** Remaining Gemini quota per API key (free tier: separate daily quota per key, reset at midnight
 * Pacific). Counts only requests this app made; Google's own page is the source of truth. */
export function GeminiQuotaList({ className }: { className?: string }) {
  const quota = useScoringQuota()
  const enable = useEnableGeminiKey()
  const q = quota.data
  if (!q || q.provider !== 'gemini' || !q.keys) return null
  const resets = q.resets_at
  return (
    <div className={cn('space-y-2', className)} data-tour="gemini-quota">
      <ul className="space-y-2">
        {q.keys.map((k) => {
          const pct = Math.min(100, Math.round((k.used / k.limit) * 100))
          return (
            <li key={k.label} className="space-y-1">
              <div className="flex items-center gap-2 text-sm">
                <KeyRound className="size-3.5 text-fg-subtle" />
                <span className="font-medium capitalize">{k.label}</span>
                <span className="font-mono text-2xs text-fg-subtle">…{k.fingerprint}</span>
                {k.state === 'ok' && <ToneBadge tone="green">Available</ToneBadge>}
                {k.state === 'exhausted' && <ToneBadge tone="amber">Used up today</ToneBadge>}
                {k.state === 'disabled' && <ToneBadge tone="red">Disabled</ToneBadge>}
                <span className="ml-auto text-xs text-fg-muted tabular-nums">
                  {k.used} / {k.limit} used · {k.remaining} left
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-surface-hover" aria-hidden>
                <div
                  className={cn('h-full rounded-full', k.state === 'disabled' ? 'bg-danger-dot' : pct >= 100 ? 'bg-warning-dot' : 'bg-success-dot')}
                  style={{ width: `${pct}%` }}
                />
              </div>
              {k.state === 'disabled' && (
                <p className="flex items-center gap-2 text-xs text-danger-fg">
                  Google refused this key: {k.reason}
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => enable.mutate(k.label, { onError: (e) => toast.error(e.message), onSuccess: () => toast.success(`${k.label} enabled again`) })}
                  >
                    Use it again
                  </Button>
                </p>
              )}
            </li>
          )
        })}
      </ul>
      <p className="text-xs text-fg-muted">
        {pluralize(q.keys.length, 'key')} · {q.remaining_today ?? 0} requests left today across enabled keys
        {resets ? ` · resets at ${clockTime(resets)} (${relativeTime(resets)})` : ''}
        {q.sample ? ' · sample data' : ''}. Free tier per key: {q.limits?.rpm}/min, {Math.round((q.limits?.tpm ?? 0) / 1000)}K tokens/min, {q.limits?.rpd}/day.
      </p>
    </div>
  )
}
