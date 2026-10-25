import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { RescoreModal } from '@/components/app/RescoreModal'
import { ToneBadge } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { pluralize } from '@/lib/format'
import { useScoringQuota, useScoringStatus } from '@/lib/queries/workflow'
import { GeminiQuotaList } from './GeminiQuota'

/** Today: how far the pass with the current prompt and model is, and what is left of the Gemini
 * quota per key. Shown only while there is something to say. */
export function ScoringTodayCard() {
  const { data } = useScoringStatus()
  const quota = useScoringQuota()
  const [confirm, setConfirm] = useState(false)
  if (!data) return null
  const isGemini = data.model.startsWith('gemini-')
  const isAPInex = data.model.startsWith('free/') || data.model.includes('minimax') || data.model.includes('deepseek')
  const hasQuota = isGemini && quota.data?.provider === 'gemini'
  const behind = data.current_total > 0 && data.current_scored < data.current_total
  if (!behind && !data.running && !hasQuota) return null
  const pct = data.current_total ? Math.round((data.current_scored / data.current_total) * 100) : 0
  return (
    <section className="rounded-lg border border-border bg-surface shadow-sm" data-tour="today-scoring">
      <div className="flex h-11 items-center gap-2 border-b border-border px-4">
        <Sparkles className="size-4 text-fg-subtle" strokeWidth={1.75} />
        <h2 className="text-sm font-semibold">Scoring</h2>
        <span className="ml-auto font-mono text-2xs text-fg-subtle">
          {data.model} · {data.prompt_version}
        </span>
      </div>
      <div className="space-y-3 px-4 py-3">
        {data.current_total > 0 && (
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">
                {pluralize(data.current_scored, 'job')} scored with the current setup
              </span>
              <span className="text-fg-muted">of {data.current_total.toLocaleString()}</span>
              <span className="ml-auto text-xs text-fg-muted tabular-nums">{pct}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-hover" aria-hidden>
              <div className="h-full rounded-full bg-primary transition-[width] duration-200" style={{ width: `${Math.max(pct, behind ? 1 : 0)}%` }} />
            </div>
            <p className="text-xs text-fg-muted">
              {data.running
                ? `Scoring now, best jobs first${data.eta_seconds ? ` (about ${Math.max(1, Math.round(data.eta_seconds / 60))} min for this batch)` : ''}.`
                : data.waiting_until
                  ? 'Waiting for the quota to reset; it continues by itself.'
                  : behind
                    ? `${pluralize(data.current_total - data.current_scored, 'job')} still on an older score.`
                    : 'Every job is on the current prompt and model.'}
            </p>
          </div>
        )}
        {isGemini && <GeminiQuotaList />}
        {isAPInex && (
          <div className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-xs text-fg-muted">
            <ToneBadge tone="green">APInex Gateway</ToneBadge>
            <span>15 RPM throttle active · Ollama fallback ready</span>
          </div>
        )}
        {behind && !data.running && !data.waiting_until && (
          <Button size="sm" onClick={() => setConfirm(true)}>
            Rescore outdated jobs…
          </Button>
        )}
      </div>
      <RescoreModal scope="outdated" open={confirm} onOpenChange={setConfirm} />
    </section>
  )
}
