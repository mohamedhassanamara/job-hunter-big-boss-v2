import { Check, ClipboardCopy, LoaderCircle, MessageSquareQuote, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/format'
import { useAskClaude, useConfirmation, useConfirmationPrompt, usePasteConfirmation } from '@/lib/queries/confirmation'
import type { ConfirmationOut, Dimension, FitBrief, JobDetail, VerdictAdvice } from '@/lib/types'
import { cn } from '@/lib/utils'
import { FitBadge, ToneBadge } from './badges'
import { ErrorState } from './states'
import { TourButton } from './tour/TourButton'

const DIMENSIONS: { key: Dimension; label: string }[] = [
  { key: 'role_match', label: 'Role' },
  { key: 'skills_match', label: 'Skills' },
  { key: 'seniority_fit', label: 'Seniority' },
  { key: 'location_eligibility', label: 'Location' },
  { key: 'language_requirements', label: 'Language' },
]

const ADVICE: Record<VerdictAdvice, { label: string; tone: 'green' | 'amber' | 'red' }> = {
  apply: { label: 'Apply', tone: 'green' },
  maybe: { label: 'Maybe', tone: 'amber' },
  skip: { label: 'Skip', tone: 'red' },
}

const SOURCE: Record<ConfirmationOut['source'], string> = {
  claude: 'Claude',
  gemma: 'Gemma (fallback)',
  manual: 'Gemini Pro app (pasted)',
  mock: 'Sample',
}

function asBrief(c: ConfirmationOut): FitBrief {
  return {
    score: c.score,
    band: c.band,
    status: 'ok',
    confidence: c.confidence,
    hard_flag: c.capped_by === 'hard_flag',
    flag_count: c.red_flags.length,
    missing_core: c.missing_core,
    stale: c.stale,
    model: c.model,
    prompt_version: c.prompt_version,
  }
}

function ManualDialog({ jobId, open, onClose }: { jobId: number; open: boolean; onClose: () => void }) {
  const prompt = useConfirmationPrompt(jobId, open)
  const paste = usePasteConfirmation(jobId)
  const [text, setText] = useState('')
  const copy = () => {
    if (!prompt.data) return
    void navigator.clipboard.writeText(prompt.data.prompt)
    toast.success('Prompt copied. Paste it into the Gemini Pro app.')
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Ask in the Gemini Pro app" className="max-w-2xl p-0">
        <div className="space-y-4 px-5 py-4">
          <div>
            <h2 className="text-md font-semibold tracking-tight">Ask in the Gemini Pro app</h2>
            <p className="text-sm text-fg-muted">
              Copy the prompt (the same scoring prompt, this job and your experience), paste it into the Gemini Pro app, then paste its JSON answer here. It is
              checked and scored like the others and stored next to the main score.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex size-5 items-center justify-center rounded-full bg-primary-subtle text-2xs font-semibold text-primary">1</span>
            <Button size="sm" onClick={copy} disabled={!prompt.data}>
              {prompt.isPending ? <LoaderCircle className="animate-spin" /> : <ClipboardCopy />}
              Copy the prompt
            </Button>
            {prompt.error && <span className="text-xs text-danger-fg">{prompt.error.message}</span>}
          </div>
          <div className="flex items-start gap-3">
            <span className="mt-1 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary-subtle text-2xs font-semibold text-primary">2</span>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the JSON answer here…" className="min-h-48 font-mono text-xs" />
          </div>
          {paste.error && <p className="text-sm text-danger-fg">{paste.error.message}</p>}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="default"
            disabled={text.trim().length < 50 || paste.isPending}
            onClick={() =>
              paste.mutate(text, {
                onSuccess: () => {
                  toast.success('Answer saved next to the main score')
                  setText('')
                  onClose()
                },
              })
            }
          >
            {paste.isPending && <LoaderCircle className="animate-spin" />}
            Save the answer
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Comparison({ job, c }: { job: JobDetail; c: ConfirmationOut }) {
  const main = job.fit_detail
  const diff = main?.score != null && c.score != null ? c.score - main.score : null
  const big = diff != null && Math.abs(diff) >= 15
  const v = c.verdict
  const advice = ADVICE[v.advice]
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 @max-sm:grid-cols-1">
        <div className="space-y-1.5 rounded-md border border-border px-3 py-2.5">
          <p className="text-xs font-semibold text-fg-muted">Main score</p>
          <div className="flex items-center gap-2">
            <FitBadge fit={main} size="lg" />
            <p className="min-w-0 truncate font-mono text-2xs text-fg-subtle">{main ? `${main.model} · ${main.prompt_version}` : ''}</p>
          </div>
        </div>
        <div className={cn('space-y-1.5 rounded-md border px-3 py-2.5', big ? 'border-tone-amber-border bg-warning-bg' : 'border-border')}>
          <p className={cn('text-xs font-semibold', big ? 'text-warning-fg' : 'text-fg-muted')}>
            Second opinion{diff != null ? `: ${diff === 0 ? 'same score' : `${diff > 0 ? '+' : ''}${diff} points`}` : ''}
          </p>
          <div className="flex items-center gap-2">
            <FitBadge fit={asBrief(c)} size="lg" />
            <p className="min-w-0 truncate font-mono text-2xs text-fg-subtle">
              {SOURCE[c.source]} · {c.model}
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-md border border-border bg-bg-subtle px-3 py-2.5" data-tour="confirm-verdict">
        <div className="mb-1 flex items-center gap-2">
          <ToneBadge tone={advice.tone}>{advice.label}</ToneBadge>
          <span className="text-sm font-medium">{v.why}</span>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
          {(
            [
              ['Seniority', v.seniority],
              ['Skills', v.skills],
              ['Location & visa', v.location_visa],
              ['Language', v.language],
            ] as const
          ).map(([k, text]) => (
            <div key={k} className="contents">
              <dt className="font-medium text-fg-muted">{k}</dt>
              <dd className="text-fg">{text}</dd>
            </div>
          ))}
        </dl>
      </div>

      {c.missing_core && (
        <p className="rounded-md border border-tone-amber-border bg-warning-bg px-3 py-2 text-xs text-warning-fg">
          Missing a core requirement: {c.missing_core}
          {c.capped_by === 'missing_core' ? ' (score capped)' : ''}
        </p>
      )}

      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-fg-subtle">
            <th className="py-1 font-medium">Sub-score</th>
            <th className="py-1 text-right font-medium">Main</th>
            <th className="py-1 text-right font-medium">Second</th>
          </tr>
        </thead>
        <tbody>
          {DIMENSIONS.map(({ key, label }) => {
            const a = main?.sub_scores[key]?.score
            const b = c.sub_scores[key]?.score
            const apart = a != null && b != null && Math.abs(a - b) >= 3
            return (
              <tr key={key} className="border-t border-border">
                <td className="py-1">{label}</td>
                <td className="py-1 text-right tabular-nums">{a ?? '–'}</td>
                <td className={cn('py-1 text-right font-medium tabular-nums', apart && 'text-warning-fg')}>{b ?? '–'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="text-xs text-fg-muted">{c.summary}</p>
      {c.notes && <p className="text-xs text-fg-subtle">{c.notes}</p>}
    </div>
  )
}

/** A second opinion next to the main score: Claude on your subscription, Gemma as the fallback,
 * and a copy-paste flow for the Gemini Pro app. It never changes the main score. */
export function ConfirmationPanel({ job, className }: { job: JobDetail; className?: string }) {
  const q = useConfirmation(job.id)
  const ask = useAskClaude(job.id)
  const [manual, setManual] = useState(false)
  const c = q.data
  const run = () => ask.mutate(undefined, { onError: () => undefined })
  const scored = job.fit_detail?.status === 'ok'
  return (
    <section className={cn('@container space-y-3 rounded-lg border border-border bg-surface p-4', className)} data-tour="job-confirm">
      <div className="flex items-center gap-2">
        <MessageSquareQuote className="size-4 text-fg-subtle" strokeWidth={1.75} />
        <h2 className="text-sm font-semibold">Second opinion</h2>
        {c && <span className="text-xs text-fg-subtle">{relativeTime(c.created_at)}{c.stale ? ' · stale' : ''}</span>}
        <div className="ml-auto flex items-center gap-1">
          {c && (
            <Button size="xs" variant="ghost" onClick={() => setManual(true)}>
              Paste from Gemini Pro
            </Button>
          )}
          <Button size="sm" variant="secondary" onClick={run} disabled={ask.isPending || !scored} data-tour="confirm-ask">
            {ask.isPending ? <LoaderCircle className="animate-spin" /> : c ? <RefreshCw /> : <Check />}
            {c ? 'Ask again' : 'Ask Claude'}
          </Button>
        </div>
      </div>

      {ask.isPending && (
        <div className="space-y-2" aria-live="polite">
          <p className="text-sm text-fg-muted">Asking Claude on your subscription… this takes about 20 to 60 seconds.</p>
          <Skeleton className="h-16 w-full" />
        </div>
      )}

      {ask.error && !ask.isPending && (
        <div className="space-y-2">
          <ErrorState compact error={ask.error} onRetry={run} />
          <Button size="sm" variant="secondary" onClick={() => setManual(true)}>
            <ClipboardCopy />
            Use the Gemini Pro app instead
          </Button>
        </div>
      )}

      {!ask.isPending && q.isPending && <Skeleton className="h-16 w-full" />}
      {!ask.isPending && q.error && <ErrorState compact error={q.error} onRetry={() => void q.refetch()} />}

      {!ask.isPending && !ask.error && q.data === null && (
        <div className="space-y-2">
          <p className="text-sm text-fg-muted">
            {scored
              ? 'Claude scores this job again with the same prompt and tells you in plain words whether to apply. It is stored next to the main score and never replaces it.'
              : 'Score this job first; the second opinion is compared with that score.'}
          </p>
          <div className="flex items-center gap-1">
            <TourButton tour="confirmation" />
            <Button size="sm" variant="ghost" onClick={() => setManual(true)}>
              Use the Gemini Pro app
            </Button>
          </div>
        </div>
      )}

      {!ask.isPending && c && <Comparison job={job} c={c} />}
      <ManualDialog jobId={job.id} open={manual} onClose={() => setManual(false)} />
    </section>
  )
}
