import { KeyRound } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { clockTime, pluralize, relativeTime } from '@/lib/format'
import { useEnableGeminiKey, usePauseGemini, useScoringQuota } from '@/lib/queries/workflow'
import { cn } from '@/lib/utils'
import { ToneBadge } from './badges'

/** Remaining Gemini quota per API key (free tier: separate daily quota per key, reset at midnight
 * Pacific). Counts only requests this app made; Google's own page is the source of truth. */
export function GeminiQuotaList({ className, model }: { className?: string; model?: string }) {
  const quota = useScoringQuota(model)
  const enable = useEnableGeminiKey()
  const pause = usePauseGemini()
  const q = quota.data
  if (!q || q.provider !== 'gemini' || !q.keys) return null
  const resets = q.resets_at
  return (
    <div className={cn('space-y-2', className)} data-tour="gemini-quota">
      {!q.sample && (
        <div className={cn('rounded-md border p-3 text-sm', q.paused ? 'border-border bg-danger-bg' : 'border-border bg-warning-bg')}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-medium">Gemini: single key, accounts under review</span>
            <span className="tabular-nums text-fg-muted">
              {q.pooled?.used ?? 0} of {q.limits?.rpd ?? 0} requests used today · {q.reserve ?? 0} kept for what you trigger · {q.limits?.rpm}/min, one at a time
            </span>
            <Button
              size="xs"
              variant={q.paused ? 'default' : 'outline'}
              className="ml-auto"
              disabled={pause.isPending}
              onClick={() =>
                pause.mutate(!q.paused, {
                  onError: (e) => toast.error(e.message),
                  onSuccess: () => toast.success(q.paused ? 'Gemini resumed' : 'Gemini paused: Claude writes CVs and emails'),
                })
              }
            >
              {q.paused ? 'Resume Gemini' : 'Pause Gemini, use Claude'}
            </Button>
          </div>
          <p className="mt-1 text-xs text-fg-muted">
            {q.keys.length > 0 ? `Using ${q.keys.map((k) => `${k.label} (…${k.last4})`).join(', ')}.` : 'No key configured.'}{' '}
            {q.paused
              ? `Paused${q.paused_reason ? `: ${q.paused_reason}` : ''}. Scoring waits; CVs and emails are written by Claude.`
              : 'If Google refuses the key even once, Gemini stops and Claude takes over.'}
          </p>
        </div>
      )}
      {q.pooled && (
        <p className="flex flex-wrap items-center gap-x-2 text-sm">
          <span className="font-medium">Pooled quota</span>
          <span className="text-fg-muted tabular-nums">
            {q.pooled.remaining} of {q.pooled.limit} requests left today across {pluralize(q.pooled.keys, 'key')}
          </span>
          <span className="text-xs text-fg-subtle">
            {q.model} · scoring, CV and email generation share it; {q.pooled.user_reserve} per key are kept for what you trigger
          </span>
        </p>
      )}
      <ul className="space-y-2">
        {q.keys.map((k) => {
          const pct = Math.min(100, Math.round((k.used / k.limit) * 100))
          return (
            <li key={k.label} className="space-y-1">
              <div className="flex items-center gap-2 text-sm">
                <KeyRound className="size-3.5 text-fg-subtle" />
                <span className="font-medium capitalize">{k.label}</span>
                <span className="font-mono text-2xs text-fg-subtle">…{k.last4}</span>
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
        {q.sample ? ' · sample data' : ''}. Limits: {q.limits?.rpm}/min, one at a time, {q.limits?.rpd}/day across every Gemini model.
      </p>
    </div>
  )
}
