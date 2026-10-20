import {
  CircleAlert,
  CircleCheck,
  CircleMinus,
  ClipboardPaste,
  Download,
  Flag,
  LoaderCircle,
  RefreshCw,
  TriangleAlert,
} from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/input'
import { Tooltip } from '@/components/ui/tooltip'
import { absoluteDate, relativeTime } from '@/lib/format'
import { useSettings } from '@/lib/queries/library'
import {
  useFetchFullListing,
  usePasteDescription,
  useRescoreJob,
  useScoringStatus,
} from '@/lib/queries/workflow'
import type { Dimension, FitDetail, JobDetail, RedFlagOut } from '@/lib/types'
import { cn } from '@/lib/utils'
import { FitBadge } from './badges'

const DIMENSIONS: { key: Dimension; label: string }[] = [
  { key: 'role_match', label: 'Role match' },
  { key: 'skills_match', label: 'Skills' },
  { key: 'seniority_fit', label: 'Seniority' },
  { key: 'location_eligibility', label: 'Location & work auth' },
  { key: 'language_requirements', label: 'Languages' },
]

const BAND_TEXT: Record<string, string> = {
  strong: 'Strong fit',
  good: 'Good fit',
  fair: 'Fair fit',
  weak: 'Weak fit',
}

const LEVEL_TEXT = {
  full: 'the full listing',
  summary: 'a summary of the listing (search index)',
  snippet: 'a short snippet of the listing',
}

const FLAG_TEXT: Record<string, string> = {
  no_visa_sponsorship: 'No visa sponsorship',
  work_authorization_required: 'Work authorization required',
  must_be_based_in: 'Must be based in a specific place',
  nationality_restricted: 'Restricted to nationals',
  language_required: 'Required language',
  seniority_mismatch: 'Seniority mismatch',
  other: 'Red flag',
}

function Quote({ text, verified }: { text: string; verified: boolean }) {
  if (!text) return <p className="text-xs text-fg-subtle italic">No supporting quote in the listing</p>
  return (
    <p className="flex items-start gap-1.5 text-xs text-fg-muted">
      <span className="border-l-2 border-border-strong pl-2 italic">“{text}”</span>
      {!verified && (
        <Tooltip content="This quote wasn't found in the listing text. The model may have paraphrased or invented it.">
          <span className="shrink-0 rounded-sm bg-warning-bg px-1 text-2xs font-medium text-warning-fg not-italic">
            Unverified
          </span>
        </Tooltip>
      )}
    </p>
  )
}

function FlagRow({ flag }: { flag: RedFlagOut }) {
  return (
    <li className="space-y-0.5">
      <p className="text-sm font-medium">
        {FLAG_TEXT[flag.type] ?? flag.type}
        <span className="font-normal text-fg-muted">: {flag.text}</span>
      </p>
      {flag.evidence && <Quote text={flag.evidence} verified={flag.evidence_verified} />}
    </li>
  )
}

function PasteDialog({ jobId, open, onClose }: { jobId: number; open: boolean; onClose: () => void }) {
  const paste = usePasteDescription()
  const [text, setText] = useState('')
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Paste the full description" className="max-w-2xl p-0">
        <div className="space-y-3 px-5 py-4">
          <div>
            <h2 className="text-md font-semibold tracking-tight">Paste the full description</h2>
            <p className="text-sm text-fg-muted">
              Open the listing, copy the whole job description and paste it here. The job is rescored
              on the full text (confidence: high).
            </p>
          </div>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste the job description…"
            className="min-h-64 text-sm"
            autoFocus
          />
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <span className="mr-auto text-xs text-fg-subtle tabular-nums">{text.length} characters</span>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="default"
            disabled={text.trim().length < 200 || paste.isPending}
            onClick={() =>
              paste.mutate(
                { jobId, description: text },
                {
                  onSuccess: () => {
                    toast.success('Description saved; rescoring on the full text')
                    setText('')
                    onClose()
                  },
                  onError: (e) => toast.error(e.message),
                },
              )
            }
          >
            Save & rescore
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Header({ fit }: { fit: FitDetail }) {
  return (
    <div className="flex items-start gap-3">
      <FitBadge fit={fit} size="lg" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">
          {fit.status === 'ok' ? BAND_TEXT[fit.band] : fit.status === 'failed' ? 'Scoring failed' : 'Not scored yet'}
          {fit.stale && <span className="ml-2 text-xs font-normal text-warning-fg">· stale</span>}
        </p>
        {fit.summary && <p className="text-sm text-fg-muted">{fit.summary}</p>}
      </div>
    </div>
  )
}

/** The fit breakdown for one job: score, confidence, red flags, sub-scores with evidence. */
export function FitCard({ job, className }: { job: JobDetail; className?: string }) {
  const fit = job.fit_detail
  const rescore = useRescoreJob()
  const fetchFull = useFetchFullListing()
  const status = useScoringStatus()
  const settings = useSettings()
  const [pasting, setPasting] = useState(false)
  const weights = (settings.data?.values.scoring?.weights ?? {}) as Partial<Record<Dimension, number>>
  const totalWeight = Object.values(weights).reduce((a, b) => a + (b ?? 0), 0) || 1
  const missingCoreCap = Number(settings.data?.values.scoring?.missing_core_cap ?? 60)
  const inQueue = !!status.data?.in_progress.some((p) => p.job_id === job.id)

  const runRescore = () =>
    rescore.mutate(job.id, {
      onSuccess: () => toast('Rescoring queued', { description: job.title }),
      onError: (e) => toast.error(e.message),
    })
  const runFetch = () =>
    fetchFull.mutate(job.id, {
      onSuccess: (r) => {
        if (r.ok) toast.success(r.message, { description: `${r.characters.toLocaleString()} characters` })
        else if (r.can_paste)
          toast(r.message, { action: { label: 'Paste it', onClick: () => setPasting(true) }, duration: 10000 })
        else toast.error(r.message)
      },
      onError: (e) => toast.error(e.message),
    })

  const hardFlags = fit?.red_flags.filter((f) => f.severity === 'hard') ?? []
  const softFlags = fit?.red_flags.filter((f) => f.severity !== 'hard') ?? []
  const missingCore = fit?.core_requirements?.filter((c) => c.counts) ?? []

  return (
    <div className={cn('@container space-y-4 rounded-lg border border-border bg-surface p-4', className)}>
      {!fit || fit.status === 'pending' ? (
        <div className="flex items-center gap-3">
          <FitBadge fit={fit} size="lg" />
          <div className="flex-1">
            <p className="text-sm font-semibold">{inQueue ? 'Scoring now…' : 'Not scored yet'}</p>
            <p className="text-sm text-fg-muted">Scores are computed in the background by your local model.</p>
          </div>
          <Button size="sm" onClick={runRescore} disabled={rescore.isPending || inQueue}>
            {inQueue ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
            Score now
          </Button>
        </div>
      ) : (
        <>
          <Header fit={fit} />

          {fit.status === 'failed' && (
            <div className="flex items-start gap-2 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger-fg">
              <CircleAlert className="mt-0.5 size-4 shrink-0" />
              <span className="flex-1 break-words">{fit.error}</span>
            </div>
          )}

          {hardFlags.length > 0 && (
            <div className="rounded-md border border-tone-red-border bg-danger-bg px-3 py-2.5">
              <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-danger-fg">
                <Flag className="size-3.5" />
                Disqualifying for you: score capped
              </p>
              <ul className="space-y-2">
                {hardFlags.map((f, i) => (
                  <FlagRow key={i} flag={f} />
                ))}
              </ul>
            </div>
          )}

          {fit.status === 'ok' && missingCore.length > 0 && (
            <div className="rounded-md border border-tone-amber-border bg-warning-bg px-3 py-2.5" data-testid="missing-core">
              <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-warning-fg">
                <TriangleAlert className="size-3.5" />
                {missingCore.length === 1 ? 'Missing a core requirement' : 'Missing core requirements'}
                {fit.capped_by === 'missing_core' ? `: score capped at ${missingCoreCap}` : ''}
              </p>
              <ul className="space-y-2">
                {missingCore.map((c) => (
                  <li key={c.requirement} className="space-y-0.5">
                    <p className="text-sm font-medium">
                      {c.requirement}
                      <span className="font-normal text-fg-muted">: nothing like it in your experience</span>
                    </p>
                    <Quote text={c.evidence} verified={c.evidence_verified} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {fit.status === 'ok' && (
            <ul className="space-y-3">
              {DIMENSIONS.map(({ key, label }) => {
                const sub = fit.sub_scores[key]
                if (!sub) return null
                const weight = weights[key] != null ? Math.round(((weights[key] ?? 0) / totalWeight) * 100) : null
                return (
                  <li key={key} className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="w-40 shrink-0 text-sm font-medium">{label}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-hover" aria-hidden>
                        <div
                          className={cn(
                            'h-full rounded-full',
                            sub.score >= 7 ? 'bg-success-dot' : sub.score >= 4 ? 'bg-warning-dot' : 'bg-danger-dot',
                          )}
                          style={{ width: `${sub.score * 10}%` }}
                        />
                      </div>
                      <span className="w-10 text-right text-sm font-semibold tabular-nums">{sub.score}/10</span>
                      {weight != null && (
                        <Tooltip content="Weight in the overall score (Settings → Scoring)">
                          <span className="w-9 text-right text-2xs text-fg-subtle tabular-nums">{weight}%</span>
                        </Tooltip>
                      )}
                    </div>
                    <p className="text-xs text-fg-muted">{sub.reason}</p>
                    <Quote text={sub.evidence} verified={sub.evidence_verified} />
                  </li>
                )
              })}
            </ul>
          )}

          {fit.status === 'ok' && (fit.strengths.length > 0 || fit.gaps.length > 0) && (
            <div className="grid gap-4 border-t border-border pt-3 @md:grid-cols-2">
              <div>
                <p className="mb-1.5 text-xs font-medium text-fg-subtle">Strengths</p>
                <ul className="space-y-1.5">
                  {fit.strengths.map((s) => (
                    <li key={s} className="flex gap-2 text-sm">
                      <CircleCheck className="mt-0.5 size-3.5 shrink-0 text-success-dot" />
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-1.5 text-xs font-medium text-fg-subtle">Gaps</p>
                {fit.gaps.length ? (
                  <ul className="space-y-1.5">
                    {fit.gaps.map((g) => (
                      <li key={g} className="flex gap-2 text-sm">
                        <CircleMinus className="mt-0.5 size-3.5 shrink-0 text-warning-dot" />
                        <span>{g}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-fg-subtle">No notable gaps</p>
                )}
              </div>
            </div>
          )}

          {softFlags.length > 0 && (
            <div className="border-t border-border pt-3">
              <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-fg-subtle">
                <TriangleAlert className="size-3.5 text-warning-dot" />
                Other flags
              </p>
              <ul className="space-y-2">
                {softFlags.map((f, i) => (
                  <FlagRow key={i} flag={f} />
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {/* Confidence + actions */}
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs text-fg-muted">
        <span>
          {fit?.status === 'ok' ? (
            <>
              Confidence <span className="font-medium text-fg">{fit.confidence}</span>: scored on{' '}
              {LEVEL_TEXT[job.description_level]}.
            </>
          ) : (
            <>We have {LEVEL_TEXT[job.description_level]}.</>
          )}
        </span>
        <div className="ml-auto flex flex-wrap gap-1">
          {job.description_level !== 'full' && (
            <>
              <Tooltip content="Fetch this one listing page and rescore on the full text">
                <Button size="xs" variant="ghost" onClick={runFetch} disabled={fetchFull.isPending}>
                  {fetchFull.isPending ? <LoaderCircle className="animate-spin" /> : <Download />}
                  Fetch full listing
                </Button>
              </Tooltip>
              <Button size="xs" variant="ghost" onClick={() => setPasting(true)}>
                <ClipboardPaste />
                Paste description
              </Button>
            </>
          )}
          {fit && fit.status !== 'pending' && (
            <Button size="xs" variant="ghost" onClick={runRescore} disabled={rescore.isPending || inQueue}>
              {inQueue ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
              {inQueue ? 'Scoring…' : 'Rescore'}
            </Button>
          )}
        </div>
      </div>
      {fit && fit.status !== 'pending' && (
        <p className="-mt-2 text-2xs text-fg-subtle">
          {fit.model} · {fit.prompt_version ?? 'no prompt version'}
          {fit.duration_ms ? ` · ${(fit.duration_ms / 1000).toFixed(1)}s` : ''} ·{' '}
          <Tooltip content={absoluteDate(fit.created_at)}>
            <span>{relativeTime(fit.created_at)}</span>
          </Tooltip>
        </p>
      )}
      <PasteDialog jobId={job.id} open={pasting} onClose={() => setPasting(false)} />
    </div>
  )
}
